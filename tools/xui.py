# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-07-05
# @Description: base on https://blog-next-js.pages.dev/blog/%E6%89%AB%E6%8F%8F%E7%BB%93%E6%9E%9C

import argparse
import base64
import gzip
import json
import os
import socket
import ssl
import threading
import time
import traceback
import typing
import urllib
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent import futures
from dataclasses import dataclass
from http.client import HTTPResponse
from urllib import parse

from geoip2 import database
from tqdm import tqdm

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

FILE_LOCK = threading.Lock()

PATH = os.path.abspath(os.path.dirname(__file__))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def http_post(url: str, headers: dict = None, params: dict = {}, retry: int = 3, timeout: float = 6) -> HTTPResponse:
    if params is None or type(params) != dict:
        return None

    timeout, retry = max(timeout, 1), retry - 1
    try:
        data = b""
        if params and isinstance(params, dict):
            data = urllib.parse.urlencode(params).encode(encoding="utf8")

        request = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
        return urllib.request.urlopen(request, timeout=timeout, context=CTX)
    except urllib.error.HTTPError as e:
        if retry < 0 or e.code in [400, 401, 405]:
            return None

        return http_post(url=url, headers=headers, params=params, retry=retry, timeout=timeout)
    except (TimeoutError, urllib.error.URLError) as e:
        return None
    except Exception:
        if retry < 0:
            return None
        return http_post(url=url, headers=headers, params=params, retry=retry, timeout=timeout)


def read_response(response: HTTPResponse, expected: int = 200, deserialize: bool = False, key: str = "") -> typing.Any:
    if not response or not isinstance(response, HTTPResponse):
        return None

    success = expected <= 0 or expected == response.getcode()
    if not success:
        return None

    try:
        text = response.read()
    except:
        text = b""

    try:
        content = text.decode(encoding="UTF8")
    except UnicodeDecodeError:
        content = gzip.decompress(text).decode("UTF8")
    except:
        content = ""

    if not deserialize:
        return content

    if not content:
        return None
    try:
        data = json.loads(content)
        return data if not key else data.get(key, None)
    except:
        return None


def trim(text: str) -> str:
    if not text or type(text) != str:
        return ""

    return text.strip()


def write_file(filename: str, lines: str | list, overwrite: bool = True) -> None:
    if not filename or not lines or type(lines) not in [str, list]:
        return

    try:
        if not isinstance(lines, str):
            lines = "\n".join(lines)

        filepath = os.path.abspath(os.path.dirname(filename))
        os.makedirs(filepath, exist_ok=True)
        mode = "w" if overwrite else "a"

        # waitting for lock
        FILE_LOCK.acquire(30)

        with open(filename, mode, encoding="UTF8") as f:
            f.write(lines + "\n")
            f.flush()

        # release lock
        FILE_LOCK.release()
    except:
        print(f"write {lines} to file {filename} failed")


def get_cookies(url: str, filepath: str, username: str = "admin", password: str = "admin") -> dict:
    url = trim(url)
    if not url:
        return None

    username = trim(username) or "admin"
    password = trim(password) or "admin"

    data = {"username": username, "password": password}
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": url,
        "Referer": url,
        "User-Agent": USER_AGENT,
    }

    response = http_post(url=f"{url}/login", headers=headers, params=data)
    success = read_response(response=response, expected=200, deserialize=True, key="success")
    if not success:
        return None

    write_file(filename=filepath, lines=url, overwrite=False)
    cookies = response.getheader("Set-Cookie")
    if not cookies:
        return None

    headers["Cookie"] = cookies
    return headers


def send_quest(url: str, subpath: str, headers: dict) -> dict:
    url = trim(url)
    if not url or not headers or not isinstance(headers, dict):
        return None

    subpath = trim(subpath)
    if subpath:
        url = parse.urljoin(url, subpath)

    response = http_post(url=url, headers=headers, params={})
    return read_response(response=response, expected=200, deserialize=True)


def get_server_status(url: str, headers: dict) -> dict:
    return send_quest(url=url, subpath="/server/status", headers=headers)


def get_inbound_list(url: str, headers: dict) -> dict:
    return send_quest(url=url, subpath="/xui/inbound/list", headers=headers)


def convert_bytes_to_readable_unit(num: int) -> str:
    TB = 1099511627776
    GB = 1073741824
    MB = 1048576

    if num >= TB:
        return f"{num / TB:.2f} TB"
    elif num >= GB:
        return f"{num / GB:.2f} GB"
    else:
        return f"{num / MB:.2f} MB"


def download_mmdb(repo: str, target: str, filepath: str, retry: int = 3):
    """
    Download GeoLite2-City.mmdb from github release
    """
    repo = trim(text=repo)
    if not repo or len(repo.split("/", maxsplit=1)) != 2:
        raise ValueError(f"invalid github repo name: {repo}")

    target = trim(target)
    if not target:
        raise ValueError("invalid download target")

    # extract download url from github release page
    release_api = f"https://api.github.com/repos/{repo}/releases/latest?per_page=1"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    }

    count, response = 0, None
    while count < retry and response is None:
        try:
            request = urllib.request.Request(url=release_api, headers=headers)
            response = urllib.request.urlopen(request, timeout=10, context=CTX)
        except Exception:
            count += 1

    assets = read_response(response=response, expected=200, deserialize=True, key="assets")
    if not assets or not isinstance(assets, list):
        raise Exception("no assets found in github release")

    download_url = ""
    for asset in assets:
        if asset.get("name", "") == target:
            download_url = asset.get("browser_download_url", "")
            break

    if not download_url:
        raise Exception("no download url found in github release")

    download(download_url, filepath, target, retry)


def download(url: str, filepath: str, filename: str, retry: int = 3) -> None:
    """Download file from url to filepath with filename"""

    if retry < 0:
        raise Exception("archieved max retry count for download")

    url = trim(url)
    if not url:
        raise ValueError("invalid download url")

    filepath = trim(filepath)
    if not filepath:
        raise ValueError("invalid save filepath")

    filename = trim(filename)
    if not filename:
        raise ValueError("invalid save filename")

    if not os.path.exists(filepath) or not os.path.isdir(filepath):
        os.makedirs(filepath)

    fullpath = os.path.join(filepath, filename)
    if os.path.exists(fullpath) and os.path.isfile(fullpath):
        os.remove(fullpath)

    # download target file from github release to fullpath
    try:
        urllib.request.urlretrieve(url=url, filename=fullpath)
    except Exception:
        return download(url, filepath, filename, retry - 1)

    print(f"download file {filename} to {fullpath} success")


def load_mmdb(
    directory: str, repo: str = "alecthw/mmdb_china_ip_list", filename: str = "Country.mmdb", update: bool = False
) -> database.Reader:
    filepath = os.path.join(directory, filename)
    if update or not os.path.exists(filepath) or not os.path.isfile(filepath):
        if not download_mmdb(repo, filename, directory):
            return None

    return database.Reader(filepath)


@dataclass
class RunningState(object):
    # 上传总流量
    sent: str = "unknown"

    # 下载总流量
    recv: str = "unknown"

    # 运行状态
    state: str = "unknown"

    # xui 版本
    version: str = "unknown"

    # 运行时间
    uptime: int = 0

    # 连接
    links: list = None


def get_running_state(data: dict) -> RunningState:
    if not data or not isinstance(data, dict) or "obj" not in data:
        return RunningState()

    uptime, sent, recv, state, version = 0, "", "", "", ""
    if "uptime" in data["obj"]:
        uptime = data["obj"]["uptime"]
    if "netTraffic" in data["obj"]:
        sent = convert_bytes_to_readable_unit(data["obj"]["netTraffic"]["sent"])
        recv = convert_bytes_to_readable_unit(data["obj"]["netTraffic"]["recv"])
    if "xray" in data["obj"]:
        state = data["obj"]["xray"]["state"]
        version = data["obj"]["xray"]["version"]

    return RunningState(sent=sent, recv=recv, state=state, version=version, uptime=uptime)


def generate_subscription_links(data: dict, address: str, reader: database.Reader) -> list[tuple[str, str, str]]:
    if not data or not isinstance(data, dict) or not data.pop("success", False) or not address:
        return []

    result = list()
    for item in data.get("obj", []):
        if not item or not isinstance(item, dict) or not item.get("enable", False):
            continue

        protocol, port, link = item["protocol"], item["port"], ""
        remark = item.get("remark", "")

        if reader:
            try:
                ip = socket.gethostbyname(address)
                response = reader.country(ip)
                country = response.country.names.get("zh-CN", "")
                if country == "中国":
                    continue

                remark = country if country else remark
            except Exception:
                pass

        if protocol == "vless":
            settings = json.loads(item["settings"])
            client_id = settings["clients"][0]["id"]
            flow = settings["clients"][0].get("flow", "")
            stream_settings = json.loads(item["streamSettings"])
            network = stream_settings["network"]
            security = stream_settings["security"]
            ws_settings = stream_settings.get("wsSettings", {})
            path = ws_settings.get("path", "/")
            query = f"type={network}&security={security}&path={parse.quote(path)}"
            if flow:
                if flow != "xtls-rprx-vision":
                    continue
                query += f"&flow={flow}"
            link = f"{protocol}://{client_id}@{address}:{port}?{query}"
        elif protocol == "vmess":
            settings = json.loads(item["settings"])
            client_id = settings["clients"][0]["id"]
            stream_settings = json.loads(item["streamSettings"])
            network = stream_settings["network"]
            ws_settings = stream_settings.get("wsSettings", {})
            path = ws_settings.get("path", "/")
            vmess_config = {
                "v": "2",
                "ps": remark or item["tag"],
                "add": address,
                "port": item["port"],
                "id": client_id,
                "aid": "0",
                "net": network,
                "type": "none",
                "host": "",
                "path": path,
                "tls": "",
            }
            link = f"vmess://{base64.urlsafe_b64encode(json.dumps(vmess_config).encode()).decode().strip('=')}"
        elif protocol == "trojan":
            settings = json.loads(item["settings"])
            client_id = settings["clients"][0]["password"]
            link = f"trojan://{client_id}@{address}:{port}"
        elif protocol == "shadowsocks":
            settings = json.loads(item["settings"])
            method = settings["method"]
            password = settings["password"]
            link = (
                f"ss://{base64.urlsafe_b64encode(f'{method}:{password}@{address}:{port}'.encode()).decode().strip('=')}"
            )

        if link:
            if remark and protocol != "vmess":
                link += f"#{remark}"

            result.append((link, item["expiryTime"], item["total"]))

    return result


def check(url: str, filepath: str, reader: database.Reader) -> RunningState:
    try:
        address = parse.urlparse(url=url).hostname
    except:
        print(f"cannot extract host from url: {url}")
        return None

    try:
        headers = get_cookies(url=url, filepath=filepath)
        status = get_server_status(url, headers)
        if not status:
            return None

        running_state = get_running_state(data=status)

        if "appStats" not in status.get("obj", {}):
            inbounds = get_inbound_list(url, headers)
            running_state.links = generate_subscription_links(data=inbounds, address=address, reader=reader)

        return running_state
    except Exception:
        return None


def multi_thread_run(
    func: typing.Callable,
    tasks: list,
    num_threads: int = None,
    show_progress: bool = False,
    description: str = "",
) -> list:
    if not func or not tasks or not isinstance(tasks, list):
        return []

    if num_threads is None or num_threads <= 0:
        num_threads = min(len(tasks), (os.cpu_count() or 1) * 2)

    funcname = getattr(func, "__name__", repr(func))

    results, starttime = [None] * len(tasks), time.time()
    with futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        if isinstance(tasks[0], (list, tuple)):
            collections = {executor.submit(func, *param): i for i, param in enumerate(tasks)}
        else:
            collections = {executor.submit(func, param): i for i, param in enumerate(tasks)}

        items = futures.as_completed(collections)
        if show_progress:
            description = trim(description) or "Progress"
            items = tqdm(items, total=len(collections), desc=description, leave=True)

        for future in items:
            try:
                result = future.result()
                index = collections[future]
                results[index] = result
            except:
                print(f"function {funcname} execution generated an exception, message:\n{traceback.format_exc()}")

    print(f"[Concurrent] execute [{funcname}] finished, count: {len(tasks)}, cost: {time.time()-starttime:.2f}s")
    return results


def extract_domain(url: str, include_protocal: bool = True) -> str:
    if not url:
        return ""

    start = url.find("//")
    if start == -1:
        start = -2

    end = url.find("/", start + 2)
    if end == -1:
        end = len(url)

    if include_protocal:
        return url[:end]

    return url[start + 2 : end]


def dedup(filepath: str) -> None:
    def include_subpath(url: str) -> bool:
        url = trim(url).lower()
        if url.startswith("http://"):
            url = url[7:]
        elif url.startswith("https://"):
            url = url[8:]

        return "/" in url and not url.endswith("/")

    def cmp(url: str) -> str:
        x = 1 if include_subpath(url=url) else 0
        y = 2 if url.startswith("https://") else 1 if url.startswith("http://") else 0
        return (x, y, url)

    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        print(f"file {filepath} not exists")
        return

    lines, groups, links = [], defaultdict(set), []
    with open(filepath, "r", encoding="utf8") as f:
        lines = f.readlines()

    # filetr and group by domain
    for line in lines:
        line = trim(line).lower()
        if not line or line.startswith("#") or line.startswith(";"):
            continue

        domain = extract_domain(url=line, include_protocal=False)
        if domain:
            if not line.startswith("https://") and not line.startswith("http://"):
                line = f"http://{line}"
                
            groups[domain].add(line)

    # under the same domain name, give priority to URLs starting with https://
    for v in groups.values():
        if not v:
            continue

        urls = list(v)
        if len(urls) > 1:
            urls.sort(key=cmp, reverse=True)

        links.append(urls[0])

    total, remain = len(lines), len(links)
    print(f"[Check] finished dedup for file: {filepath}, total: {total}, remain: {remain}, drop: {total-remain}")

    write_file(filename=filepath, lines=links, overwrite=True)


def generate_markdown(items: list[RunningState], filepath: str) -> None:
    if not items or not isinstance(items, list) or not filepath:
        return

    headers = ["XRay状态", "XRay版本", "运行时间", "上行总流量", "下行总流量", "订阅链接"]

    table = "| " + " | ".join(headers) + " |\n"
    table += "| " + " | ".join(["---"] * len(headers)) + " |\n"

    for item in items:
        if not isinstance(item, RunningState):
            continue

        link = "<br />".join([x[0] for x in item.links])
        table += f"| {item.state} | {item.version} | {item.uptime} | {item.sent} | {item.recv} | {link} |\n"

    write_file(filename=filepath, lines=table, overwrite=True)


def main(args: argparse.Namespace) -> None:
    workspace = os.path.abspath(trim(args.workspace) or PATH)

    source = os.path.join(workspace, trim(args.filename))
    if not os.path.exists(source) or not os.path.isfile(source):
        print(f"scan failed due to file {source} not exist")
        return

    dedup(filepath=source)

    domains = []
    with open(source) as f:
        domains = [x for x in f.readlines() if x and not x.startswith("#")]

    if not domains:
        print("skip scan due to empty domain list")
        return

    # load mmdb
    reader = load_mmdb(directory=workspace, update=args.update)

    available = os.path.join(workspace, trim(args.available))
    tasks = [[domain, available, reader] for domain in domains]

    print(f"start to scan domains, total: {len(tasks)}")
    result = multi_thread_run(func=check, tasks=tasks, num_threads=args.thread, show_progress=not args.invisible)

    effectives, links = [], []
    for item in result:
        if not item or not isinstance(item, RunningState) or not item.links:
            continue

        effectives.append(item)
        links.extend([x[0] for x in item.links])

    if links:
        filename = os.path.join(workspace, trim(args.link) or "links.txt")
        print(f"found {len(links)} links, save it to {filename}")

        content = base64.b64encode("\n".join(links).encode(encoding="utf8")).decode(encoding="utf8")
        write_file(filename=filename, lines=content, overwrite=True)

    markdown = os.path.join(workspace, trim(args.markdown) or "table.md")
    generate_markdown(items=effectives, filepath=markdown)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-a",
        "--available",
        type=str,
        required=False,
        default="availables.txt",
        help="save correct username password filename",
    )

    parser.add_argument(
        "-f",
        "--filename",
        type=str,
        required=True,
        help="domain list filename",
    )

    parser.add_argument(
        "-i",
        "--invisible",
        dest="invisible",
        action="store_true",
        default=False,
        help="don't show check progress bar",
    )

    parser.add_argument(
        "-l",
        "--link",
        type=str,
        required=False,
        default="links.txt",
        help="link list filename",
    )

    parser.add_argument(
        "-m",
        "--markdown",
        type=str,
        required=False,
        default="table.md",
        help="markdown filename for result",
    )

    parser.add_argument(
        "-t",
        "--thread",
        type=int,
        required=False,
        default=0,
        help="number of concurrent threads, defaults to double the number of CPU cores",
    )

    parser.add_argument(
        "-u",
        "--update",
        dest="update",
        action="store_true",
        default=False,
        help="whether to update the IP database",
    )

    parser.add_argument(
        "-w",
        "--workspace",
        type=str,
        default=PATH,
        required=False,
        help="workspace absolute path",
    )

    main(parser.parse_args())
