# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import itertools
import json
import os
import random
import re
import ssl
import string
import urllib
import urllib.parse
from collections import defaultdict

import executable
import utils
import yaml
from logger import logger
from outbound import QuotedStr, endpoint_key, proxy_exists, quoted_scalar

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

DOWNLOAD_URL = [
    "https://github.com/2dust/v2rayN/releases/latest/download/v2rayN.zip",
    "https://cachefly.cachefly.net/10mb.test",
    "http://speedtest-sgp1.digitalocean.com/10mb.test",
]

EXTERNAL_CONTROLLER = "127.0.0.1:9090"


def generate_config(path: str, proxies: list[dict[str, object]], filename: str) -> list[dict[str, object]]:
    os.makedirs(path, exist_ok=True)
    external_config = filter_proxies(proxies)
    config = {
        "mixed-port": 7890,
        "external-controller": EXTERNAL_CONTROLLER,
        "mode": "Rule",
        "log-level": "silent",
    }

    config.update(external_config)
    with open(os.path.join(path, filename), "w+", encoding="utf8") as f:
        # avoid mihomo error: invalid REALITY short ID see: https://github.com/MetaCubeX/mihomo/blob/Meta/adapter/outbound/reality.go#L35
        yaml.add_representer(QuotedStr, quoted_scalar)

        # write to file
        yaml.dump(config, f, allow_unicode=True)

    return config.get("proxies", [])


def filter_proxies(proxies: list[dict[str, object]]) -> dict[str, object]:
    config = {
        "proxies": [],
        "proxy-groups": [
            {
                "name": "automatic",
                "type": "url-test",
                "proxies": [],
                "url": "https://www.google.com/favicon.ico",
                "interval": 300,
            },
            {"name": "🌐 Proxy", "type": "select", "proxies": ["automatic"]},
        ],
        "rules": ["MATCH,🌐 Proxy"],
    }

    # 按名字排序方便在节点相同时优先保留名字靠前的
    proxies.sort(key=lambda p: str(p.get("name", "")))
    unique_proxies, hosts = [], defaultdict(list)

    for item in proxies:
        if not proxy_exists(item, hosts):
            unique_proxies.append(item)
            key = endpoint_key(item)
            hosts[key].append(item)

    # 防止多个代理节点名字相同导致clash配置错误
    groups, unique_names = {}, set()
    for key, group in itertools.groupby(unique_proxies, key=lambda p: p.get("name", "")):
        items = groups.get(key, [])
        items.extend(list(group))
        groups[key] = items

    # 优先保留不重复的节点的名字
    unique_proxies = sorted(groups.values(), key=lambda x: len(x))
    proxies.clear()
    for items in unique_proxies:
        size = len(items)
        if size <= 1:
            proxies.extend(items)
            unique_names.add(items[0].get("name"))
            continue
        for i in range(size):
            item = items[i]
            mode = i % 26
            factor = i // 26 + 1
            letter = string.ascii_uppercase[mode]
            name = "{}-{}{}".format(item.get("name"), factor, letter)
            while name in unique_names:
                mode += 1
                factor = factor + mode // 26
                mode = mode % 26
                letter = string.ascii_uppercase[mode]
                name = "{}-{}{}".format(item.get("name"), factor, letter)

            item["name"] = name
            proxies.append(item)
            unique_names.add(name)

    # shuffle
    for _ in range(3):
        random.shuffle(proxies)

    config["proxies"] += proxies
    config["proxy-groups"][0]["proxies"] += list(unique_names)
    config["proxy-groups"][1]["proxies"] += list(unique_names)

    return config


def check(
    proxy: dict[str, object], api_url: str, timeout: int, test_url: str, delay: int, strict: bool = False
) -> bool:
    proxy_name = ""
    try:
        proxy_name = urllib.parse.quote(proxy.get("name", ""), safe="")
    except:
        logger.debug(f"encoding proxy name error, proxy: {proxy.get('name', '')}")
        return False

    base_url = f"http://{api_url}/proxies/{proxy_name}/delay?timeout={str(timeout)}&url="

    # 失败重试间隔：30ms ~ 200ms
    interval = random.randint(30, 200) / 1000
    targets = [
        test_url,
        "https://www.youtube.com/s/player/23010b46/player_ias.vflset/en_US/remote.js",
    ]
    if strict:
        targets.append(random.choice(DOWNLOAD_URL))
    try:
        alive, allowed = True, False
        trace = os.getenv("FOOL_PROOF", "").lower() in ["true", "1"]

        if trace:
            # prevents liveness check from being terminated due to a long period of time with no output
            logger.info(f"start liveness check, proxy: {proxy.get('name', '')}")

        for target in targets:
            target = urllib.parse.quote(target)
            url = f"{base_url}{target}"
            content = utils.http_get(url=url, retry=2, interval=interval, trace=trace)
            try:
                data = json.loads(content)
            except:
                data = {}

            if data.get("delay", -1) <= 0 or data.get("delay", -1) > delay:
                alive = False
                break

        return alive
    except Exception as e:
        logger.debug(f"check failed, proxy: {proxy.get('name')}, message: {str(e)}")
        return False


def is_mihomo() -> bool:
    base = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    clash_bin, _ = executable.which_bin()
    binpath = os.path.join(base, "clash", clash_bin)

    try:
        utils.chmod(binpath)
        _, output = utils.cmd([binpath, "-v"], True)
        return re.search("Mihomo Meta", output, flags=re.I) is not None
    except:
        return False
