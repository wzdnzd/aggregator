# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-05-20

import argparse
import gzip
import itertools
import json
import multiprocessing
import os
import re
import ssl
import sys
import time
import typing
import urllib
import urllib.parse
import urllib.request
import warnings
from copy import deepcopy
from multiprocessing.managers import ListProxy
from multiprocessing.synchronize import Semaphore

import yaml

warnings.filterwarnings("ignore")

HEADER = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36 Edg/100.0.1185.39",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "zh-CN,zh;q=0.9",
    "dnt": "1",
    "Connection": "keep-alive",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "x-requested-with": "XMLHttpRequest",
}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

PATH = os.path.abspath(os.path.dirname(__file__))

"""
原理: https://bulianglin.com/archives/getnodelist.html
"""


def convert(chars: bytes, filepath: str = "", persist: bool = False, includes: str = "all") -> list:
    if chars is None or b"" == chars:
        return []

    if includes not in ["vmess", "ssr", "all"]:
        print("not support protocal: {}".format(includes))
        return []

    try:
        contents = json.loads(chars).get("nodeinfo", None)
        if not contents:
            print("cannot fetch node list, response: {}".format(chars))
            return []

        nodes_muport = contents["nodes_muport"]
        if not nodes_muport:
            return []

        if persist and filepath:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w+") as f:
                f.write(chars.decode("unicode_escape"))
                f.flush()

        params = []
        for nm in nodes_muport:
            uuid = ""
            customer = {}
            user = nm.get("user")
            if not user:
                continue

            uuid = user.get("uuid", "")
            properties = [
                "id",
                "passwd",
                "method",
                "protocol",
                "protocol_param",
                "obfs",
                "obfs_param",
                "port",
            ]
            for k in properties:
                customer[k] = user.get(k, "")

            if not uuid:
                print("[warning] uuid is empty")

            params.append((uuid, customer))

        arrays = []
        nodes = contents["nodes"]
        for node in nodes:
            if node["online"] != -1:
                for ps in params:
                    result = parse(node["raw_node"], ps[0], ps[1], includes)
                    if result:
                        arrays.append(result)
        return arrays
    except Exception as e:
        print("convert failed: {}".format(str(e)))
        return []


def parse_v2ray(node: dict, uuid: str) -> dict:
    if not uuid:
        return None

    result = {
        "name": node.get("name"),
        "type": "vmess",
        "uuid": uuid,
        "cipher": "auto",
        "skip-cert-verify": True,
    }

    server = node.get("server")
    if "tls" in server:
        print("tls: {}".format(server))

    items = server.split(";")
    result["alterId"] = int(items[2])

    network = items[3].strip()
    if network == "" or "tls" in network:
        network = items[4].strip()
    result["network"] = network
    result["tls"] = "tls" in items[3] or "tls" in items[4]

    host = items[0]
    port = int(items[1])

    if len(items) > 5:
        obfs = items[5]
        opts = {}
        if obfs != None and obfs.strip() != "":
            for s in obfs.split("|"):
                words = s.split("=")
                if len(words) != 2:
                    continue

                if words[0] == "server":
                    host = words[1]
                elif words[0] == "outside_port":
                    port = int(words[1])
                elif words[0] == "path":
                    opts["path"] = words[1]
                elif words[0] == "host":
                    opts["headers"] = {"Host": words[1]}

        if opts:
            result["ws-opts"] = opts

    result["server"] = host
    result["port"] = port
    return result


def parse_ssr(node: dict, user: dict) -> dict:
    host = ""
    port = int(user["port"])

    server = node.get("server", "")
    # https://github.com/EmiyaTKK/Malio-Theme-for-SSPANEL/blob/54d85d75a180a198a7a46800738e8de0c95f1cd5/app/Utils/Tools.php#L607
    if ";" not in server:
        host = server
    else:
        contents = server.split(";")
        host = contents[0]
        words = contents[1].split("|")
        ans = {}
        for word in words:
            if "=" not in word:
                continue
            kv = word.split("=")
            ans[kv[0]] = kv[1]

        # host = ans.get("server", host)
        chars = ans.get("port", "")
        if "#" not in chars:
            port += int(chars)
        else:
            if "+" not in chars:
                arrays = chars.split("#")
                # port = int(array[1]) if port == int(arrays[0]) else port
                if int(arrays[0]) == port:
                    port = int(arrays[1])
            else:
                arrays = chars.split("+")
                for arr in arrays:
                    sl = arr.split("#")
                    if port == int(sl[0]):
                        port = int(sl[1])
                        break

    if user.get("obfs", "") == "tls1.2_ticket_auth_compatible":
        user["obfs"] = "tls1.2_ticket_auth"

    item = {
        "name": node.get("name"),
        "server": host,
        "port": port,
        "type": "ssr",
        "cipher": user["method"],
        "password": user["passwd"],
        "protocol": user["protocol"],
        "obfs": user["obfs"],
        "protocol-param": "{}:{}".format(user["id"], user["passwd"]),
        "obfs-param": user["obfs_param"],
    }

    item["server"] = host
    item["port"] = port
    return item


def parse(node: dict, uuid: str, user: dict = None, includes: str = "all") -> dict:
    def get_protocal(num: int) -> str:
        if num in [0, 10, 13]:
            return "ssr"
        elif num in [11, 12]:
            return "vmess"
        elif num == 14:
            return "trojan"
        else:
            return "unknow"

    if not node:
        return None

    # https://github.com/EmiyaTKK/Malio-Theme-for-SSPANEL/blob/54d85d75a180a198a7a46800738e8de0c95f1cd5/app/Utils/URL.php#L242
    num = int(node["sort"])
    protocal = get_protocal(num)
    if protocal == "vmess" and includes in ["vmess", "all"]:
        return parse_v2ray(node, uuid)
    elif protocal == "ssr" and includes in ["ssr", "all"]:
        return parse_ssr(node, user)
    elif protocal == "unknow":
        print("cannot parse, server={}\ttype={}".format(node.get("server"), protocal))

    return None


def login(url, params, headers, retry) -> str:
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        if response.getcode() == 200:
            return response.getheader("Set-Cookie")
        else:
            print("[LoginError]: {}".format(response.read().decode("unicode_escape")))
            return ""

    except Exception as e:
        print("[LoginError]: {}".format(str(e)))

        retry -= 1
        return login(url, params, headers, retry) if retry > 0 else ""


def register(url: str, params: dict, retry: int) -> bool:
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, method="POST", headers=HEADER)

        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        if response.getcode() == 200:
            content = response.read()
            kv = json.loads(content)
            if "ret" in kv and kv["ret"] == 1:
                return True

        print("[ScanerRegisterError] domain: {}, message: {}".format(url, response.read().decode("unicode_escape")))
        return False
    except Exception as e:
        print("[ScanerRegisterError] domain: {}, message: {}".format(url, str(e)))

        retry -= 1
        return register(url, params, retry) if retry > 0 else False


def reload(url: str, config: str) -> None:
    if not (os.path.exists(config) and os.path.isfile(config)):
        print("config file not exists, path: {}".format(config))
        return

    header = {"Content-Type": "application/json"}
    params = {"path": config}

    try:
        data = bytes(json.dumps(params), encoding="utf8")
        request = urllib.request.Request(url, data=data, headers=header, method="PUT")

        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        if response.getcode() == 204:
            print("reload clash successed")
        else:
            print(response.read().decode("UTF8"))

    except Exception as e:
        print(str(e))


def get_cookie(text) -> str:
    regex = "(__cfduid|uid|email|key|ip|expire_in)=(.+?);"
    if not text:
        return ""

    content = re.findall(regex, text)
    cookie = ";".join(["=".join(x) for x in content]).strip()

    return cookie


def fetch_nodes(domain: str, email: str, passwd: str, headers: dict = None, retry: int = 3) -> bytes:
    headers = deepcopy(HEADER) if not headers else headers
    login_url = domain + "/auth/login"
    headers["origin"] = domain
    headers["referer"] = login_url
    user_info = {"email": email, "passwd": passwd}

    text = login(login_url, user_info, headers, 3)
    cookie = get_cookie(text)
    if not text or len(cookie) <= 0:
        return None

    headers["cookie"] = cookie
    content = None
    while retry > 0 and not content:
        retry -= 1
        try:
            request = urllib.request.Request(domain + "/getnodelist", headers=headers)
            response = urllib.request.urlopen(request, timeout=30, context=CTX)
            if response.getcode() == 200:
                content = response.read()
                break
            else:
                print(
                    "[ScanerFetchError] domain: {}, message: {}".format(
                        domain, response.read().decode("unicode_escape")
                    )
                )
        except Exception as e:
            print("[ScanerFetchError] domain: {}, message: {}".format(domain, str(e)))

    return content


def check(domain: str) -> bool:
    try:
        content = http_get(url=domain + "/getnodelist", headers=HEADER)
        if content:
            data = json.loads(content)
            return "ret" in data and data["ret"] == -1
    except:
        pass

    return False


def extract_domain(url) -> str:
    if not url or not re.match(
        "^(https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+)(:\d+)?(\/.*)?(\?.*)?(#.*)?$",
        url,
    ):
        return ""

    start = url.find("//")
    if start == -1:
        start = -2

    end = url.find("/", start + 2)
    if end == -1:
        end = len(url)

    return url[:end]


def scan(domain: str, file: str, args: argparse.Namespace) -> None:
    # 检测是否符合条件
    if not check(domain):
        print("cannot crack, domain: {}".format(domain))
        return

    if not args.skip and "@" in args.email:
        register_url = domain + "/auth/register"
        params = {
            "name": args.email.split("@")[0],
            "email": args.email,
            "passwd": args.passwd,
            "repasswd": args.passwd,
        }

        # 注册失败后不立即返回 因为可能已经注册过
        if not register(register_url, params, 3):
            print("[ScanerError] register failed, domain: {}".format(domain))

    # 获取机场所有节点信息
    content = fetch_nodes(domain, args.email, args.passwd)
    filepath = os.path.join(args.path, "{}.json".format(domain.split("/")[2]))
    nodes = convert(content, filepath, args.keep, args.type)
    if not nodes:
        return

    proxies = {"proxies": nodes}

    if not file:
        print(json.dumps(proxies))
        return

    os.makedirs(os.path.dirname(file), exist_ok=True)
    with open(file, "w+", encoding="utf-8") as f:
        yaml.dump(proxies, f, allow_unicode=True)

    print("found {} nodes, domain: {}".format(len(nodes), domain))


def encoding_url(url: str) -> str:
    if not url:
        return ""

    url = url.strip()

    # 正则匹配中文汉字
    cn_chars = re.findall("[\u4e00-\u9fa5]+", url)
    if not cn_chars:
        return url

    # 遍历进行 punycode 编码
    punycodes = list(map(lambda x: "xn--" + x.encode("punycode").decode("utf-8"), cn_chars))

    # 对原 url 进行替换
    for c, pc in zip(cn_chars, punycodes):
        url = url[: url.find(c)] + pc + url[url.find(c) + len(c) :]

    return url


def http_get(
    url: str,
    headers: dict = None,
    params: dict = None,
    retry: int = 3,
    proxy: str = "",
    interval: float = 1,
) -> str:
    if not re.match(
        "^(https?:\/\/(\S+\.)+[a-zA-Z]+)(:\d+)?(\/.*)?(\?.*)?(#.*)?$",
        url,
    ):
        return ""

    if retry <= 0:
        return ""

    if not headers:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.27",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        }

    interval = max(0, interval)
    try:
        url = encoding_url(url=url)
        if params and isinstance(params, dict):
            data = urllib.parse.urlencode(params)
            if "?" in url:
                url += f"&{data}"
            else:
                url += f"?{data}"

        request = urllib.request.Request(url=url, headers=headers)
        if proxy and (proxy.startswith("https://") or proxy.startswith("http://")):
            host, protocal = "", ""
            if proxy.startswith("https://"):
                host, protocal = proxy[8:], "https"
            else:
                host, protocal = proxy[7:], "http"
            request.set_proxy(host=host, type=protocal)

        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        content = response.read()
        status_code = response.getcode()
        try:
            content = str(content, encoding="utf8")
        except:
            content = gzip.decompress(content).decode("utf8")
        if status_code != 200:
            return ""

        return content
    except urllib.error.HTTPError as e:
        message = str(e.read(), encoding="utf8")
        if e.code == 503 and "token" not in message:
            time.sleep(interval)
            return http_get(
                url=url,
                headers=headers,
                params=params,
                retry=retry - 1,
                proxy=proxy,
                interval=interval,
            )
        return ""
    except urllib.error.URLError as e:
        return ""
    except Exception as e:
        time.sleep(interval)
        return http_get(
            url=url,
            headers=headers,
            params=params,
            retry=retry - 1,
            proxy=proxy,
            interval=interval,
        )


def get_telegram_pages(channel: str) -> int:
    if not channel or channel.strip() == "":
        return 0

    url = f"https://t.me/s/{channel}"
    content = http_get(url=url)
    before = 0
    try:
        regex = f'<link\s+rel="canonical"\s+href="/s/{channel}\?before=(\d+)">'
        groups = re.findall(regex, content)
        before = int(groups[0]) if groups else before
    except:
        print(f"[CrawlError] cannot count page num, chanel: {channel}")

    return before


def extract_airport_site(url: str) -> list:
    if not url:
        return []

    content = http_get(url=url)
    if not content:
        print(f"[CrawlError] cannot any content from url: {url}")
        return []
    try:
        regex = 'href="(https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+/?)"\s+target="_blank"\s+rel="noopener">'
        groups = re.findall(regex, content)
        return list(set(groups)) if groups else []
    except:
        return []


def crawl_channel(channel: str, page_num: int, fun: typing.Callable) -> list:
    """crawl from telegram channel"""
    if not channel or not fun or not isinstance(fun, typing.Callable):
        return []

    print(f"[TelegramCrawl] starting crawl from telegram, channel: {channel}, pages: {page_num}")

    page_num = max(page_num, 1)
    url = f"https://t.me/s/{channel}"
    if page_num == 1:
        return list(fun(url))
    else:
        count = get_telegram_pages(channel=channel)
        if count == 0:
            return []

        pages = range(count, -1, -20)
        page_num = min(page_num, len(pages))
        urls = [f"{url}?before={x}" for x in pages[:page_num]]

        cpu_count = multiprocessing.cpu_count()
        num = len(urls) if len(urls) <= cpu_count else cpu_count

        pool = multiprocessing.Pool(num)
        results = pool.map(fun, urls)
        pool.close()

        return list(itertools.chain.from_iterable(results))


def collect_airport(channel: str, page_num: int, thread_num: int = 50) -> list:
    domains = crawl_channel(channel=channel, page_num=page_num, fun=extract_airport_site)

    if not domains:
        return []

    with multiprocessing.Manager() as manager:
        availables = manager.list()
        processes = []
        semaphore = multiprocessing.Semaphore(thread_num)
        for domain in list(set(domains)):
            semaphore.acquire()
            p = multiprocessing.Process(target=validate_domain, args=(domain, availables, semaphore))
            p.start()
            processes.append(p)
        for p in processes:
            p.join()

        domains = list(availables)
        print(
            f"[AirPortCollector] finished collect air port from telegram channel: {channel}, availables: {len(domain)}"
        )
        return domains


def validate_domain(url: str, availables: ListProxy, semaphore: Semaphore) -> None:
    try:
        if not url or not check(url):
            return

        availables.append(url)
    finally:
        if semaphore is not None and isinstance(semaphore, Semaphore):
            semaphore.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-r",
        "--reload",
        dest="reload",
        action="store_true",
        help="reload clash config if true",
    )

    parser.add_argument("-s", "--skip", dest="skip", action="store_true", help="skip register")

    parser.add_argument(
        "-b",
        "--batch",
        dest="batch",
        action="store_true",
        help="read domains from file and batch check",
    )

    parser.add_argument(
        "-k",
        "--keep",
        dest="keep",
        action="store_true",
        help="save nodes list information if true",
    )

    parser.add_argument(
        "-a",
        "--address",
        type=str,
        required=False,
        default="",
        help="airport domain",
    )

    parser.add_argument(
        "-e",
        "--email",
        type=str,
        required=False,
        default="",
        help="username or email",
    )

    parser.add_argument("-p", "--passwd", type=str, required=False, default="", help="password")

    parser.add_argument(
        "-t",
        "--type",
        type=str,
        required=False,
        choices=["vmess", "ssr", "all"],
        default="vmess",
        help="include node type",
    )

    parser.add_argument(
        "-f",
        "--file",
        type=str,
        required=False,
        default="",
        help="subscribe file saved path",
    )

    parser.add_argument(
        "-u",
        "--url",
        type=str,
        required=False,
        default="http://127.0.0.1:9090/configs?force=true",
        help="clash controller api",
    )

    parser.add_argument(
        "-d",
        "--path",
        type=str,
        required=False,
        default=PATH,
        help="directory for save result",
    )

    parser.add_argument(
        "-c",
        "--config",
        type=str,
        required=False,
        default="",
        help="clash config path",
    )

    args = parser.parse_args()

    if args.batch:
        if not args.address or args.address.startswith("http://") or args.address.startswith("https://"):
            raise ValueError("local file path cannot be url")

        if not (os.path.exists(args.address) and os.path.isfile(args.address)):
            print("select batch mode, but file not found, path: {}, begin crawl from telegram".format(args.address))
            domains = collect_airport(channel="jichang_list", page_num=sys.maxsize)
            if not domains:
                sys.exit(-1)

            os.makedirs(os.path.abspath(os.path.dirname(args.address)), exist_ok=True)
            with open(args.address, "w+", encoding="UTF8") as f:
                f.write("\n".join(domains))
                f.flush()

        tasks = []
        with open(args.address, "r") as f:
            for line in f.readlines():
                domain = extract_domain(line)
                if not domain:
                    print("skip invalidate domain, url: {}".format(line))
                    continue

                filepath = os.path.join(args.path, "{}.yaml".format(domain.split("/")[2]))
                tasks.append((domain, filepath, args))

        import multiprocessing

        cpu_count = multiprocessing.cpu_count()
        num = len(tasks) if len(tasks) <= cpu_count else cpu_count

        pool = multiprocessing.Pool(num)
        pool.starmap(scan, tasks)
        pool.close()
    else:
        domain = extract_domain(args.address)
        if not domain:
            print("skip invalidate domain, url: {}".format(args.address))
            sys.exit(-1)

        scan(domain, args.file, args)

    # 重载clash配置
    if args.reload:
        reload(args.url, args.config)
