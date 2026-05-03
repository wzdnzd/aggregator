# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2023-07-10

import argparse
import gzip
import json
import multiprocessing
import os
import ssl
import sys
import time
import typing
import urllib
import urllib.parse
import urllib.request
from dataclasses import dataclass

import psutil
import yaml

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.27"


DEFAULT_HTTP_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
}

PATH = os.path.abspath(os.path.dirname(__file__))


@dataclass
class APIConfig(object):
    # config file path
    path: str

    # auth token
    secret: str

    # external controller api address
    controller: str

    # provider name and file path
    providers: list[tuple[str, str]]


def parse(base: str, filename: str, provider: str = "", all: bool = False) -> APIConfig:
    filepath = os.path.abspath(os.path.join(base, filename))
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        print(f"cannot load config due to file {filepath} not found")
        return None

    provider = trim(provider)
    if not provider and not all:
        print(f"specify the provider name or use '--all' to test all providers")
        return None

    with open(filepath, "r", encoding="utf8") as f:
        try:
            data = yaml.load(f, Loader=yaml.SafeLoader)
            secret = trim(data.get("secret", ""))
            controller = trim(data.get("external-controller", "127.0.0.1:9090"))
            providers = [
                (k, os.path.abspath(os.path.join(base, v.get("path", ""))))
                for k, v in data.get("proxy-providers", {}).items()
            ]
            if provider:
                providers = [x for x in providers if x[0] == provider]

            return APIConfig(
                path=filepath,
                secret=secret,
                controller=complete(controller),
                providers=providers,
            )
        except Exception as e:
            print(f"parse config file {filepath} error, message: {str(e)}")
            return None


def http_get(url: str, headers: dict = None, retry: int = 3, timeout: int = 6) -> tuple[int, str]:
    if not url or retry <= 0:
        return 400, ""

    timeout = max(timeout, 1)
    headers = DEFAULT_HTTP_HEADERS if not headers else headers

    try:
        request = urllib.request.Request(url=url, headers=headers)
        response = urllib.request.urlopen(request, timeout=timeout, context=CTX)
        status, content = response.getcode(), ""
        if status == 200:
            content = response.read()
            try:
                content = str(content, encoding="utf8")
            except:
                content = gzip.decompress(content).decode("utf8")

        return status, content
    except:
        return http_get(url=url, headers=headers, retry=retry - 1, timeout=timeout)


def fetch_proxies(prefix: str, provider: str, headers: dict, retry: int = 3) -> list[dict]:
    url = f"{prefix}/providers/proxies/{provider}"
    _, content = http_get(url=url, headers=headers, retry=retry, timeout=30)
    try:
        return json.loads(content).get("proxies", [])
    except:
        return []


def statistics(prefix: str, provider: str, headers: dict, base: int, retry: int = 3) -> tuple[bool, int]:
    proxies = fetch_proxies(prefix, provider, headers, retry)
    if not proxies:
        return False, 0

    n, found, wait = min(20, len(proxies)), False, 240
    for i in range(n):
        history = proxies[i].get("history", [])
        if len(history) >= base:
            found = True
            break

    samples = [1.0, 0.75, 0.50, 0.25]
    for num in samples:
        index = max(0, int(len(proxies) * num) - 1)
        history = proxies[index].get("history", [])
        if len(history) >= base:
            wait = int(wait * (1 - num)) + 10
            break

    return found, wait


def healthcheck(prefix: str, provider: str, headers: dict, retry: int = 3) -> bool:
    prefix, provider = trim(prefix), trim(provider)
    if not prefix or not provider or retry <= 0:
        return False

    url = f"{prefix}/providers/proxies/{provider}/healthcheck"
    status, _ = http_get(url=url, headers=headers, timeout=15)
    return status in [200, 204]


def reload(prefix: str, secret: str, retry: int = 3) -> bool:
    prefix, secret = trim(prefix), trim(secret)
    if not prefix or retry <= 0:
        return False

    url = f"{prefix}/configs?force=true"
    headers = get_headers(secret=secret)

    data = bytes(json.dumps({"path": "", "payload": ""}), encoding="utf8")
    success, count = False, 0
    while not success and count < retry:
        try:
            request = urllib.request.Request(url, data=data, headers=headers, method="PUT")
            response = urllib.request.urlopen(request, timeout=10, context=CTX)
            if response.getcode() == 204:
                success = True
        except:
            pass

        count += 1
    return success


def get_headers(secret: str = "") -> dict:
    headers = {"Content-Type": "application/json"}

    secret = trim(secret)
    if secret:
        headers["Authorization"] = f"Bearer {secret}"

    return headers


def trim(text: str) -> str:
    if not text or type(text) != str:
        return ""

    return text.strip()


def complete(url: str) -> str:
    if not url:
        return ""

    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"http://{url}"

    return url


def copy(filepath: str) -> None:
    if not filepath or not os.path.exists(filepath) or not os.path.isfile(filepath):
        return

    newfile = f"{filepath}.bak"
    if os.path.exists(newfile):
        os.remove(newfile)

    os.rename(filepath, newfile)


def running(name):
    name = trim(name)
    for proc in psutil.process_iter():
        try:
            if name.lower() in proc.name().lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    return False


def batch(func: typing.Callable, params: list) -> list:
    if not func or not params or type(params) != list:
        return []

    cpu_count = multiprocessing.cpu_count()
    num = len(params) if len(params) <= cpu_count else cpu_count

    pool = multiprocessing.Pool(num)
    if type(params[0]) == list or type(params[0]) == tuple:
        results = pool.starmap(func, params)
    else:
        results = pool.map(func, params)
    pool.close()

    return results


def process(
    prefix: str,
    secret: str,
    provider: str,
    filepath: str,
    backup: bool,
    iteration: int,
    delay: int,
) -> bool:
    headers = get_headers(secret)

    ok, count = False, 0
    # health check
    while not ok and count < iteration:
        ok, wait = statistics(prefix, provider, headers, iteration, 3)
        if not ok:
            healthcheck(prefix, provider, headers, 3)
            count += 1
            time.sleep(wait)

    collections = fetch_proxies(prefix, provider, headers, 3)
    if not collections:
        return False

    names, nodes = set(), []
    for p in collections:
        name, history = p.get("name", ""), p.get("history", [])
        if not history or not p.get("alive", False):
            names.add(name)
            continue

        keys, result = ["delay", "meanDelay"], [0] * 4
        for h in history:
            for i in range(len(keys)):
                d = h.get(keys[i], 0)
                if d > 0:
                    result[2 * i] += d
                    result[2 * i + 1] += 1

        m, n = result[1], result[3]
        m = 1 if m == 0 else m
        n = 1 if n == 0 else n
        v = (result[0] / m + result[2] / n) / 2
        if v <= 0 or v > delay:
            names.add(name)

    if len(names) == 0:
        return False

    with open(filepath, "r", encoding="utf8") as f:
        try:
            nodes = yaml.load(f, Loader=yaml.SafeLoader).get("proxies", [])
        except (yaml.constructor.ConstructorError, yaml.parser.ParserError):
            yaml.add_multi_constructor("str", lambda loader, suffix, node: str(node.value), Loader=yaml.SafeLoader)
            nodes = yaml.load(f, Loader=yaml.FullLoader).get("proxies", [])

    proxies = [x for x in nodes if x.get("name", "") not in names]
    if not proxies:
        return False

    print(f"completed filtering, total: {len(nodes)}, filtered: {len(names)}, remain: {len(proxies)}")

    data = {"proxies": proxies}
    if backup:
        copy(filepath)
    with open(filepath, "w+", encoding="utf8") as f:
        yaml.dump(data, f, allow_unicode=True)

    return True


def main(args: argparse.Namespace) -> None:
    if not running("clash.exe"):
        print(f"cannot check and filter proxies due to clash.exe is not running")
        sys.exit(-1)

    base, filename = trim(args.workspace), trim(args.config)
    config = parse(base, filename, args.provider, args.all)
    if not config or not config.controller or not config.providers:
        print(f"skip filter because config is invalid or proxy provider not exists")
        sys.exit(-1)

    delay, providers = max(1, args.delay), config.providers
    tasks = [
        [
            config.controller,
            config.secret,
            x[0],
            x[1],
            args.backup,
            args.iteration,
            delay,
        ]
        for x in providers
    ]

    result = batch(func=process, params=tasks)
    if not any(result):
        print(f"filter proxy providers error, providers: {[x[0] for x in providers]}")
        sys.exit(-1)

    message = "success" if reload(config.controller, config.secret) else "failed"
    print(f"reload clash.exe with config {config.path} {message}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-a",
        "--all",
        dest="all",
        action="store_true",
        default=False,
        help="Check and filter all proxy providers",
    )

    parser.add_argument(
        "-b",
        "--backup",
        dest="backup",
        action="store_true",
        default=False,
        help="Backup old provider file",
    )

    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default="config.yaml",
        required=False,
        help="Clash configuration filename",
    )

    parser.add_argument(
        "-d",
        "--delay",
        type=int,
        default=600,
        required=False,
        help="Maximum acceptable delay",
    )

    parser.add_argument(
        "-i",
        "--iteration",
        type=int,
        default=6,
        required=False,
        choices=range(1, 11),
        help="Health check iteration",
    )

    parser.add_argument(
        "-p",
        "--provider",
        type=str,
        required=False,
        default="",
        help="Proxy provider name to be check and filtered",
    )

    parser.add_argument(
        "-w",
        "--workspace",
        type=str,
        default=PATH,
        required=False,
        help="Workspace absolute path",
    )

    main(parser.parse_args())
