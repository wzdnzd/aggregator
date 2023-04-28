# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import itertools
import json

# import multiprocessing
import os
import platform
import random
import ssl
import string
import sys
import urllib
import urllib.parse
import urllib.request
from multiprocessing.managers import DictProxy, ListProxy
from multiprocessing.synchronize import Semaphore

import yaml

import utils
from logger import logger

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

DOWNLOAD_URL = [
    "https://github.com/2dust/v2rayN/releases/latest/download/v2rayN.zip",
    "https://cachefly.cachefly.net/10mb.test",
    "http://speedtest-sgp1.digitalocean.com/10mb.test",
]

EXTERNAL_CONTROLLER = "127.0.0.1:9090"


def generate_config(path: str, proxies: list, filename: str) -> list:
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
        yaml.dump(config, f, allow_unicode=True)

    return config.get("proxies", [])


def filter_proxies(proxies: list) -> dict:
    ss_supported_ciphers = [
        "aes-128-gcm",
        "aes-192-gcm",
        "aes-256-gcm",
        "aes-128-cfb",
        "aes-192-cfb",
        "aes-256-cfb",
        "aes-128-ctr",
        "aes-192-ctr",
        "aes-256-ctr",
        "rc4-md5",
        "chacha20-ietf",
        "xchacha20",
        "chacha20-ietf-poly1305",
        "xchacha20-ietf-poly1305",
    ]
    ssr_supported_obfs = [
        "plain",
        "http_simple",
        "http_post",
        "random_head",
        "tls1.2_ticket_auth",
        "tls1.2_ticket_fastauth",
    ]
    ssr_supported_protocol = [
        "origin",
        "auth_sha1_v4",
        "auth_aes128_md5",
        "auth_aes128_sha1",
        "auth_chain_a",
        "auth_chain_b",
    ]
    vmess_supported_ciphers = ["auto", "aes-128-gcm", "chacha20-poly1305", "none"]
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
    sorted(proxies, key=lambda p: p.get("name", ""))
    unique_proxies = []
    for item in proxies:
        try:
            authentication = "password"
            item["port"] = int(item["port"])
            if item["type"] == "ss":
                if item["cipher"] not in ss_supported_ciphers:
                    continue
            elif item["type"] == "ssr":
                if item["cipher"] not in ss_supported_ciphers:
                    continue
                if item["obfs"] not in ssr_supported_obfs:
                    continue
                if item["protocol"] not in ssr_supported_protocol:
                    continue
            elif item["type"] == "vmess":
                authentication = "uuid"
                if "udp" in item and item["udp"] not in [False, True]:
                    continue
                if "tls" in item and item["tls"] not in [False, True]:
                    continue
                if "skip-cert-verify" in item and item["skip-cert-verify"] not in [
                    False,
                    True,
                ]:
                    continue
                if item["cipher"] not in vmess_supported_ciphers:
                    continue
            elif item["type"] == "trojan":
                if "udp" in item and item["udp"] not in [False, True]:
                    continue
                if "skip-cert-verify" in item and item["skip-cert-verify"] not in [
                    False,
                    True,
                ]:
                    continue
            elif item["type"] == "snell":
                authentication = "psk"
                if "udp" in item and item["udp"] not in [False, True]:
                    continue
                if "skip-cert-verify" in item and item["skip-cert-verify"] not in [
                    False,
                    True,
                ]:
                    continue
            elif item["type"] == "http":
                authentication = "userpass"
                if "tls" in item and item["tls"] not in [False, True]:
                    continue
            elif item["type"] == "socks5":
                authentication = "userpass"
                if "tls" in item and item["tls"] not in [False, True]:
                    continue
                if "udp" in item and item["udp"] not in [False, True]:
                    continue
                if "skip-cert-verify" in item and item["skip-cert-verify"] not in [
                    False,
                    True,
                ]:
                    continue
            else:
                continue

            if not item[authentication] or proxies_exists(item, unique_proxies):
                continue

            unique_proxies.append(item)
        except:
            continue

    # 防止多个代理节点名字相同导致clash配置错误
    groups, unique_names = {}, set()
    for key, group in itertools.groupby(
        unique_proxies, key=lambda p: p.get("name", "")
    ):
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

    config["proxies"] += proxies
    config["proxy-groups"][0]["proxies"] += list(unique_names)
    config["proxy-groups"][1]["proxies"] += list(unique_names)

    return config


def proxies_exists(proxy: dict, proxies: list) -> bool:
    if not proxy:
        return True
    if not proxies:
        return False

    duplicate = False
    protocal = proxy.get("type", "")
    if protocal == "ss" or protocal == "trojan":
        duplicate = any(
            p.get("server", "").lower() == proxy.get("server", "").lower()
            and p.get("port", 0) == proxy.get("port", 0)
            and p.get("password", "").lower() == proxy.get("password", "").lower()
            for p in proxies
        )
    elif protocal == "ssr":
        duplicate = any(
            p.get("server", "").lower() == proxy.get("server", "").lower()
            and p.get("port", 0) == proxy.get("port", 0)
            and p.get("protocol-param", "").lower()
            == proxy.get("protocol-param", "").lower()
            for p in proxies
        )
    elif protocal == "vmess":
        duplicate = any(
            p.get("server", "").lower() == proxy.get("server", "").lower()
            and p.get("port", 0) == proxy.get("port", 0)
            and p.get("uuid", "").lower() == proxy.get("uuid", "").lower()
            for p in proxies
        )
    elif protocal == "snell":
        duplicate = any(
            p.get("server", "").lower() == proxy.get("server", "").lower()
            and p.get("port", 0) == proxy.get("port", 0)
            and p.get("psk", "").lower() == proxy.get("psk", "").lower()
            for p in proxies
        )
    elif protocal == "http" or protocal == "socks5":
        duplicate = any(
            p.get("server", "").lower() == proxy.get("server", "").lower()
            and p.get("port", 0) == proxy.get("port", 0)
            for p in proxies
        )

    return duplicate


def check(
    availables: ListProxy,
    proxy: dict,
    api_url: str,
    semaphore: Semaphore,
    timeout: int,
    test_url: str,
    delay: int,
    validates: DictProxy,
    strict: bool = False,
) -> None:
    proxy_name = urllib.parse.quote(proxy.get("name", ""))
    base_url = (
        f"http://{api_url}/proxies/{proxy_name}/delay?timeout={str(timeout)}&url="
    )

    # 失败重试间隔：30ms ~ 200ms
    interval = random.randint(30, 200) / 1000
    targets = [
        test_url,
        "https://www.youtube.com/s/player/23010b46/player_ias.vflset/en_US/remote.js",
    ]
    if strict:
        targets.append(random.choice(DOWNLOAD_URL))
    try:
        alive = True
        for target in targets:
            target = urllib.parse.quote(target)
            url = f"{base_url}{target}"
            content = utils.http_get(url=url, retry=2, interval=interval)
            try:
                data = json.loads(content)
            except:
                data = {}

            if data.get("delay", -1) <= 0 or data.get("delay", -1) > delay:
                alive = False
                break

        if alive:
            # filter and check US(for speed) proxies as candidates for ChatGPT/OpenAI/New Bing/Google Bard
            proxy_name = proxy.get("name", "")
            if utils.PATTERN_AI.search(proxy_name):
                try:
                    request = urllib.request.Request(
                        url=f"{base_url}https://chat.openai.com/favicon.ico",
                        headers=utils.DEFAULT_HTTP_HEADERS,
                    )
                    response = urllib.request.urlopen(request, timeout=10, context=CTX)
                    if response.getcode() == 200 and not proxy_name.endswith(
                        utils.CHATGPT_FLAG
                    ):
                        proxy["name"] = f"{proxy_name}{utils.CHATGPT_FLAG}"
                except Exception:
                    pass

            sub = proxy.pop("sub", "")
            availables.append(proxy)
            if validates != None and sub:
                validates[sub] = True
    except:
        pass
    finally:
        if semaphore is not None and isinstance(semaphore, Semaphore):
            semaphore.release()


def which_bin() -> tuple[str, str]:
    operating_system = str(platform.platform())
    if operating_system.startswith("macOS"):
        if "arm64" in operating_system:
            clashname = "clash-darwin-arm"
        else:
            clashname = "clash-darwin-arm"

        subconverter = "subconverter-mac"
    elif operating_system.startswith("Linux"):
        clashname = "clash-linux"
        subconverter = "subconverter-linux"
    elif operating_system.startswith("Windows"):
        clashname = "clash-windows.exe"
        subconverter = "subconverter-windows.exe"
    else:
        logger.error("Unsupported Platform")
        sys.exit(1)

    return clashname, subconverter
