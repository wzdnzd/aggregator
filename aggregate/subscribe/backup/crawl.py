# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import argparse
import itertools
import json
import multiprocessing
import re
import ssl
import sys
import time
import urllib
import urllib.parse
import urllib.request
import urllib.error
import string
import random

import time
import datetime


CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def crawl(userid: str, period: int):
    if not userid:
        return []

    now = time.time() - 3600 * 12
    crawl_time = datetime.datetime.fromtimestamp(now).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"https://telemetr.io/post-list-ajax/{userid}/with-date-panel?period={period}&date={crawl_time}"

    content = http_get(url=url)
    if content == "":
        return []

    regex = "https?://\S+/api/v1/client/subscribe\?token=[a-zA-Z0-9]+|https?://\S+/link/[a-zA-Z0-9]+\?sub=\d"
    subscribes = re.findall(regex, content)

    array = []
    for s in subscribes:
        # 强制使用https协议
        s = s.replace("http://", "https://", 1)

        if "token=" in s:
            s += "&flag=v2ray"
        if validate(s):
            array.append(s)

    return set(array)


def http_get(url: str, headers: dict = None, retry: int = 3) -> str:
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


def validate(url: str) -> bool:
    return http_get(url=url, retry=2) != ""


def push(content: str, folderid: str, fileid: str, key: str, retry: int = 5) -> bool:
    if "" == key.strip() or "" == fileid.strip():
        return False

    if content.strip() == "":
        content = " "

    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    data = json.dumps({"content": {"format": "text", "value": content}}).encode("UTF8")
    url = f"https://api.paste.gg/v1/pastes/{folderid}/files/{fileid}"

    try:
        request = urllib.request.Request(
            url, data=data, headers=headers, method="PATCH"
        )
        response = urllib.request.urlopen(request, context=CTX)
        if response.getcode() == 204:
            print(f"[PushSuccess] push subscribes information to remote successed")
            return True
        else:
            print(
                "[PushError]: error message: {}".format(
                    response.read().decode("unicode_escape")
                )
            )
            return False

    except Exception as e:
        print("[PushError]: error message: {}".format(e))
        retry -= 1
        if retry > 0:
            return push(content, folderid, fileid, key, retry)

        return False


def load_pushconf(url: str) -> dict:
    if not re.match(
        "^(https?:\/\/(([a-zA-Z0-9]+-?)+[a-zA-Z0-9]+\.)+[a-zA-Z]+)(:\d+)?(\/.*)?(\?.*)?(#.*)?$",
        url,
    ):
        print(f"invalidate push config url, url= {url}")
        return {}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.114 Safari/537.36 Edg/103.0.1264.62",
        "Referer": url,
    }

    content = http_get(url=url, headers=headers)
    try:
        return json.loads(content)
    except Exception:
        return {}


def extract_name(url):
    if not url:
        return ""

    start = url.find("//")
    if start == -1:
        start = -2

    end = url.find(".", start + 2)
    if end == -1:
        end = len(url) - 1

    return url[start + 2 : end] + "".join(
        random.sample(
            string.ascii_letters + string.digits + string.ascii_lowercase,
            random.randint(3, 5),
        )
    )


def validate_push(config: dict, include_name: bool = True) -> bool:
    if not config:
        return False

    ans = (
        config.get("folderid", "")
        and config.get("fileid", "")
        and config.get("key", "")
    )

    if include_name:
        ans = ans and config.get("username", "")

    return ans


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-u",
        "--users",
        type=str,
        required=False,
        default="1627048316,1338209352,1446619448,1613641779",
        help="telegram chanels id",
    )

    parser.add_argument(
        "-p",
        "--period",
        type=int,
        required=False,
        choices=[7, 30, 180],
        default=7,
        help="period",
    )

    parser.add_argument(
        "-s",
        "--server",
        type=str,
        required=False,
        default="https://sharetext.me/raw/4mligqxk6a",
        help="push config url",
    )

    parser.add_argument(
        "-c",
        "--collection",
        type=str,
        required=False,
        default="shared",
        help="subscribe collection name",
    )

    args = parser.parse_args()
    if not args.users or not args.server or not args.collection:
        sys.exit(0)

    push_confs = load_pushconf(args.server)
    push_subscribes = push_confs.get("subscribes", {})
    push_tasks = push_confs.get("proxies", {})
    if not validate_push(push_subscribes, False) or not validate_push(push_tasks, True):
        print("cannot startup crawl task because push configs error")
        sys.exit(0)

    print("starting to crawl subscribe from telegram")
    users = set(args.users.split(","))
    params = [(u, args.period) for u in users]
    cpu_count = multiprocessing.cpu_count()
    num = len(params) if len(params) <= cpu_count else cpu_count

    pool = multiprocessing.Pool(num)
    results = pool.starmap(crawl, params)
    pool.close()

    subscribes = set(list(itertools.chain.from_iterable(results)))
    tasks = []
    for s in subscribes:
        task = {"name": extract_name(s), "sub": s, "push_to": [args.collection]}
        tasks.append(task)

    dataset = {"domains": tasks}
    dataset["push"] = {args.collection: push_tasks}
    content = json.dumps(dataset)
    push(
        content,
        push_subscribes.get("folderid"),
        push_subscribes.get("fileid"),
        push_subscribes.get("key"),
    )

    print(f"finished crawl subscribe from telegram, found [{len(tasks)}]")
