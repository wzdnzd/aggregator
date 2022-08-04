# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import os
import platform
import random
import re
import ssl
import string
import subprocess
import sys
import urllib
import urllib.parse
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def random_chars(length: int, punctuation: bool = False) -> str:
    length = max(length, 1)
    if punctuation:
        chars = "".join(
            random.sample(
                string.ascii_letters + string.digits + string.punctuation, length
            )
        )
    else:
        chars = "".join(random.sample(string.ascii_letters + string.digits, length))

    return chars


def http_get(
    url: str, headers: dict = None, params: dict = None, retry: int = 3
) -> str:
    if not re.match(
        "^(https?:\/\/(\S+\.)+[a-zA-Z]+)(:\d+)?(\/.*)?(\?.*)?(#.*)?$",
        url,
    ):
        print(f"invalid url: {url}")
        return ""

    if retry <= 0:
        print(f"achieves max retry, url={url}")
        return ""

    if not headers:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.114 Safari/537.36 Edg/103.0.1264.62",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        }

    try:
        if params:
            data = urllib.parse.urlencode(params)
            if "?" in url:
                url += f"&{data}"
            else:
                url += f"?{data}"

        request = urllib.request.Request(url=url, headers=headers)
        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        status_code = response.getcode()
        content = str(response.read(), encoding="utf8")
        if status_code != 200:
            print(f"request failed, status code: {status_code}\t message: {content}")
            return ""

        return content
    except urllib.error.HTTPError as e:
        print(f"request failed, url=[{url}], code: {e.code}")
        message = str(e.read(), encoding="utf8")
        if e.code == 503 and "token" not in message:
            return http_get(url, headers, retry - 1)
        return ""
    except urllib.error.URLError as e:
        print(f"request failed, url=[{url}], message: {e.reason}")
        return ""
    except Exception:
        return http_get(url, headers, retry - 1)


def extract_domain(url: str, include_protocal: bool = False) -> str:
    if not url:
        return ""

    start = url.find("//")
    if start == -1:
        start = -2

    end = url.find("/", start + 2)
    if end == -1:
        end = len(url) - 1

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


def cmd(command: list) -> bool:
    if command is None or len(command) == 0:
        return False

    print("command: {}".format(" ".join(command)))

    p = subprocess.Popen(command)
    p.wait()
    return p.returncode == 0


def chmod(binfile: str) -> None:
    if not os.path.exists(binfile) or os.path.isdir(binfile):
        raise ValueError(f"cannot found bin file: {binfile}")

    operating_system = str(platform.platform())
    if operating_system.startswith("Windows"):
        return
    elif operating_system.startswith("macOS") or operating_system.startswith("Linux"):
        cmd(["chmod", "+x", binfile])
    else:
        print("Unsupported Platform")
        sys.exit(0)
