# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import gzip
import json
import multiprocessing
import os
import platform
import random
import re
import socket
import ssl
import string
import subprocess
import sys
import time
import traceback
import typing
import urllib
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent import futures
from http.client import HTTPMessage, HTTPResponse

from logger import logger
from tqdm import tqdm
from urlvalidator import isurl

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)


# 本地路径协议标识
FILEPATH_PROTOCAL = "file:///"


# ChatGPT 标识
CHATGPT_FLAG = "-GPT"


DEFAULT_HTTP_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
}


def random_chars(length: int, punctuation: bool = False) -> str:
    length = max(length, 1)
    if punctuation:
        chars = "".join(random.sample(string.ascii_letters + string.digits + string.punctuation, length))
    else:
        chars = "".join(random.sample(string.ascii_letters + string.digits, length))

    return chars


def http_get(
    url: str,
    headers: dict = None,
    params: dict = None,
    retry: int = 3,
    proxy: str = "",
    interval: float = 0,
    timeout: float = 10,
    trace: bool = False,
    max_size=None,
) -> str:
    if not isurl(url=url):
        logger.error(f"invalid url: {url}")
        return ""

    if retry <= 0:
        logger.debug(f"achieves max retry, url={hide(url=url)}")
        return ""

    headers = DEFAULT_HTTP_HEADERS if not headers else headers

    interval = max(0, interval)
    timeout = max(1, timeout)
    length = None if max_size is None or max_size <= 0 else max_size

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

        response = urllib.request.urlopen(request, timeout=timeout, context=CTX)
        content = response.read(length)
        status_code = response.getcode()
        try:
            content = str(content, encoding="utf8")
        except:
            content = gzip.decompress(content).decode("utf8")
        if status_code != 200:
            if trace:
                logger.error(f"request failed, url: {hide(url)}, code: {status_code}, message: {content}")

            return ""

        return content
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, ssl.SSLError)):
            time.sleep(interval)
            return http_get(
                url=url,
                headers=headers,
                params=params,
                retry=retry - 1,
                proxy=proxy,
                interval=interval,
                timeout=timeout,
                max_size=length,
            )
        else:
            return ""
    except Exception as e:
        if trace:
            logger.error(f"request failed, url: {hide(url)}, message: \n{traceback.format_exc()}")

        if isinstance(e, urllib.error.HTTPError):
            try:
                message = str(e.read(), encoding="utf8")
            except:
                message = "unknown error"

            if e.code != 503 or "token" in message:
                return ""

        time.sleep(interval)
        return http_get(
            url=url,
            headers=headers,
            params=params,
            retry=retry - 1,
            proxy=proxy,
            interval=interval,
            timeout=timeout,
            max_size=length,
        )


def extract_domain(url: str, include_protocal: bool = False) -> str:
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


def extract_cookie(text: str) -> str:
    # ?: 标识后面的内容不是一个group
    regex = "((?:v2board)?_session)=((?:.+?);|.*)"
    if not text:
        return ""

    content = re.findall(regex, text)
    cookie = ";".join(["=".join(x) for x in content]).strip()
    return cookie


def cmd(command: list, output: bool = False) -> tuple[bool, str]:
    if command is None or len(command) == 0:
        return False, ""

    p = (
        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if output
        else subprocess.Popen(command)
    )
    p.wait()

    success, content = p.returncode == 0, ""
    if output:
        try:
            content = p.stdout.read().decode("utf8")
        except:
            content = ""
    return success, content


def chmod(binfile: str) -> None:
    if not os.path.exists(binfile) or os.path.isdir(binfile):
        raise ValueError(f"cannot found bin file: {binfile}")

    operating_system = str(platform.platform())
    if operating_system.startswith("Windows"):
        return
    elif operating_system.startswith("macOS") or operating_system.startswith("Linux"):
        cmd(["chmod", "+x", binfile])
    else:
        logger.error("Unsupported Platform")
        sys.exit(0)


def encoding_url(url: str) -> str:
    if not url:
        return ""

    url = url.strip()

    # 解析URL获取各个部分
    try:
        result = urllib.parse.urlparse(url)
        domain = result.netloc
        path = result.path
        query = result.query
        fragment = result.fragment

        # 处理域名部分（可能包含端口号）
        if re.search("[\u4e00-\u9fa5]", domain):
            if ":" in domain:
                host, port = domain.split(":", 1)
                # 对域名部分进行Punycode编码
                host = host.encode("idna").decode("utf-8")
                # 重新组合域名和端口
                domain = f"{host}:{port}"
            else:
                # 直接对整个域名进行Punycode编码
                domain = domain.encode("idna").decode("utf-8")

        # 处理路径部分，对非ASCII字符进行URL编码
        if re.search("[\u4e00-\u9fa5]", path):
            # 对路径中的中文字符进行URL编码
            path = urllib.parse.quote(path, safe="/")

        # 处理查询参数部分，保留查询参数的结构
        if query and re.search("[\u4e00-\u9fa5]", query):
            # 解析查询参数
            query_dict = urllib.parse.parse_qs(query)
            # 对每个参数值进行URL编码
            encoded_query_dict = {}
            for key, values in query_dict.items():
                encoded_query_dict[key] = [urllib.parse.quote(v, safe="") for v in values]
            # 重新组合查询参数
            query = urllib.parse.urlencode(encoded_query_dict, doseq=True)

        # 处理片段部分
        if fragment and re.search("[\u4e00-\u9fa5]", fragment):
            fragment = urllib.parse.quote(fragment)

        # 重新组装URL
        url = urllib.parse.urlunparse(
            (
                result.scheme,
                domain,
                path,
                result.params,
                query,
                fragment,
            )
        )

        return url
    except Exception as e:
        logger.error(f"Error encoding URL: {url}, error: {str(e)}")
        return url


def write_file(filename: str, lines: list) -> bool:
    if not filename or not lines:
        logger.error(f"filename or lines is empty, filename: {filename}")
        return False

    try:
        if not isinstance(lines, str):
            lines = "\n".join(lines)

        filepath = os.path.abspath(os.path.dirname(filename))
        os.makedirs(filepath, exist_ok=True)
        with open(filename, "w+", encoding="UTF8") as f:
            f.write(lines)
            f.flush()

        return True
    except:
        return False


def isb64encode(content: str, padding: bool = True) -> bool:
    if not content:
        return False

    # 判断是否为base64编码
    regex = "^([A-Za-z0-9+/]{4})*([A-Za-z0-9+/]{4}|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{2}==)$"

    # 不是标准base64编码的情况，padding
    b64flag = re.match(regex, content)
    if not b64flag and len(content) % 4 != 0 and padding:
        content += "=" * (4 - len(content) % 4)
        b64flag = re.match(regex, content)

    return b64flag is not None


def isblank(text: str) -> bool:
    return not text or type(text) != str or not text.strip()


def trim(text: str) -> str:
    if not text or type(text) != str:
        return ""

    return text.strip()


def load_dotenv(enviroment: str = ".env") -> None:
    path = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    enviroment = trim(enviroment) or ".env"
    filename = os.path.join(path, enviroment)

    if not os.path.exists(filename) or os.path.isdir(filename):
        return

    with open(filename, mode="r", encoding="utf8") as f:
        for line in f.readlines():
            content = line.strip()
            if not content or content.startswith("#") or "=" not in content:
                continue

            content = content.split("#", maxsplit=1)[0]
            words = content.split("=", maxsplit=1)
            k, v = words[0].strip(), words[1].strip()
            if k and v:
                os.environ[k] = v


def hide(url: str) -> str:
    # len('http://') equals 7
    if isblank(url) or len(url) < 7:
        return url

    return url[:-7] + "*" * 7


def parse_token(url: str) -> str:
    if not isurl(url):
        return ""

    result = urllib.parse.urlparse(url=url)
    if result.query:
        params = {k: v[0] for k, v in urllib.parse.parse_qs(result.query).items()}
        if "token" in params:
            return params.get("token", "")

    group = re.findall(".*/link/([a-zA-Z0-9]+)", url, flags=re.I)
    content = trim(group[0]) if group else ""
    return content.lower() if content else url.lower()


def mask(url: str) -> str:
    url = trim(text=url)
    try:
        parse_result = urllib.parse.urlparse(url=url)
        if "token=" in parse_result.query:
            token = "".join(re.findall("token=([a-zA-Z0-9]+)", parse_result.query))
            if len(token) >= 6:
                token = token[:3] + "***" + token[-3:]
            url = f"{parse_result.scheme}://{parse_result.netloc}{parse_result.path}?token={token}"
        else:
            path, token = parse_result.path.rsplit("/", maxsplit=1)
            if len(token) >= 6:
                token = token[:3] + "***" + token[-3:]
            url = f"{parse_result.scheme}://{parse_result.netloc}{path}/{token}"
    except:
        logger.error(f"invalid url: {url}")

    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def http_error_302(
        self,
        req: urllib.request.Request,
        fp: typing.IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
    ) -> typing.IO[bytes]:
        return fp


def http_post(
    url: str,
    headers: dict = None,
    params: dict = {},
    retry: int = 3,
    timeout: float = 6,
    allow_redirects: bool = True,
) -> HTTPResponse:
    if params is None or type(params) != dict or retry <= 0:
        return None

    timeout, retry = max(timeout, 1), retry - 1
    if not headers:
        headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        }
    try:
        data = json.dumps(params).encode(encoding="UTF8")
        request = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
        if allow_redirects:
            return urllib.request.urlopen(request, timeout=timeout, context=CTX)

        opener = urllib.request.build_opener(NoRedirect)
        return opener.open(request, timeout=timeout)
    except Exception:
        time.sleep(random.random())
        return http_post(
            url=url,
            headers=headers,
            params=params,
            retry=retry,
            allow_redirects=allow_redirects,
        )


def verify_uuid(text: str) -> bool:
    if not text or type(text) != str:
        return False

    try:
        _ = uuid.UUID(text)
        return True
    except ValueError:
        return False


def is_number(num: str) -> bool:
    try:
        float(num)
        return True
    except ValueError:
        return False


def url_complete(url: str, secret: bool = False) -> str:
    if isblank(url):
        return ""

    if not url.startswith("https://"):
        # force use https protocol
        if url.startswith("http://"):
            if secret:
                url = url.replace("http://", "https://")
        else:
            url = f"https://{url}"

    return url


def load_emoji_pattern(filepath: str = "") -> dict:
    filepath = trim(filepath)
    if not filepath:
        workspace = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        filepath = os.path.join(workspace, "subconverter", "snippets", "emoji.txt")

    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        logger.warning(f"cannot parse emoji config due to file {filepath} not exists")
        return {}

    # see: https://github.com/tindy2013/subconverter/blob/master/base/snippets/emoji.txt
    patterns = {}
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f.readlines():
            line = trim(line)
            if not line or line.startswith("#"):
                continue

            try:
                regex, emoji = line.rsplit(",", maxsplit=1)
                pattern = re.compile(regex, flags=re.I)
                patterns[pattern] = emoji
            except ValueError:
                logger.warning(f"cannot parse emoji config due to invalid line: {line}")

    return patterns


def get_emoji(text: str, patterns: dict, default: str = "") -> str:
    if not patterns or type(patterns) != dict or not text or type(text) != str:
        return default

    for pattern, emoji in patterns.items():
        if pattern.search(text):
            return emoji

    return default


def get_subpath(api_prefix: str, default: str = "/api/v1/") -> str:
    path = trim(api_prefix) or trim(default) or "/api/v1/"
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("=") and not path.endswith("/"):
        path += "/"

    return path


def multi_process_run(func: typing.Callable, tasks: list) -> list:
    if not func or not isinstance(func, typing.Callable):
        logger.error(f"skip execute due to func is not callable")
        return []

    if not tasks or type(tasks) != list:
        logger.error(f"skip execute due to tasks is empty or invalid")
        return []

    cpu_count = multiprocessing.cpu_count()
    num = len(tasks) if len(tasks) <= cpu_count else cpu_count

    starttime, results = time.time(), []

    # TODO: handle KeyboardInterrupt and exit program immediately
    with multiprocessing.Pool(num) as pool:
        try:
            if isinstance(tasks[0], (list, tuple)):
                results = pool.starmap(func, tasks)
            else:
                results = pool.map(func, tasks)
        except KeyboardInterrupt:
            logger.error(f"the tasks has been cancelled and the program will exit now")

            pool.terminate()
            pool.join()

    funcname = getattr(func, "__name__", repr(func))
    logger.info(
        f"[Concurrent] multi-process concurrent execute [{funcname}] finished, count: {len(tasks)}, cost: {time.time()-starttime:.2f}s"
    )

    return results


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

            # TODO: use p_tqdm instead of tqdm, see https://github.com/swansonk14/p_tqdm
            items = tqdm(items, total=len(collections), desc=description, leave=True)

        for future in items:
            try:
                result = future.result()
                index = collections[future]
                results[index] = result
            except Exception as e:
                logger.error(f"function {funcname} execution generated an exception: {e}")

    logger.info(
        f"[Concurrent] multi-threaded execute [{funcname}] finished, count: {len(tasks)}, cost: {time.time()-starttime:.2f}s"
    )

    return results
