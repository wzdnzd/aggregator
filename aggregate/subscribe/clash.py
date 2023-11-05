# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import itertools
import json

# import multiprocessing
import os
import random
import ssl
import string
import urllib
import urllib.parse
import urllib.request
from collections import defaultdict
from multiprocessing.managers import DictProxy, ListProxy
from multiprocessing.synchronize import Semaphore

import utils
import yaml

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
        if verify(item) and not proxies_exists(item, hosts):
            unique_proxies.append(item)
            key = f"{item.get('server')}:{item.get('port')}"
            hosts[key].append(item)

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


def proxies_exists(proxy: dict, hosts: dict) -> bool:
    if not proxy:
        return True
    if not hosts:
        return False

    key = f"{proxy.get('server')}:{proxy.get('port')}"
    proxies = hosts.get(key, [])

    if not proxies:
        return False

    protocol = proxy.get("type", "")
    if protocol == "http" or protocol == "socks5":
        return True
    elif protocol == "ss" or protocol == "trojan":
        return any(p.get("password", "") == proxy.get("password", "") for p in proxies)
    elif protocol == "ssr":
        return any(
            str(p.get("protocol-param", "")).lower()
            == str(proxy.get("protocol-param", "")).lower()
            for p in proxies
        )
    elif protocol == "vmess" or protocol == "vless":
        return any(p.get("uuid", "") == proxy.get("uuid", "") for p in proxies)
    elif protocol == "snell":
        return any(p.get("psk", "") == proxy.get("psk", "") for p in proxies)

    return False


SS_SUPPORTED_CIPHERS = [
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
SSR_SUPPORTED_OBFS = [
    "plain",
    "http_simple",
    "http_post",
    "random_head",
    "tls1.2_ticket_auth",
    "tls1.2_ticket_fastauth",
]
SSR_SUPPORTED_PROTOCOL = [
    "origin",
    "auth_sha1_v4",
    "auth_aes128_md5",
    "auth_aes128_sha1",
    "auth_chain_a",
    "auth_chain_b",
]
VMESS_SUPPORTED_CIPHERS = ["auto", "aes-128-gcm", "chacha20-poly1305", "none"]


def verify(item: dict) -> bool:
    if not item or type(item) != dict:
        return False

    try:
        # name must be string
        name = str(item.get("name", "")).strip().upper()
        if not name:
            return False

        item["name"] = name

        # server must be string
        server = str(item.get("server", "")).strip().lower()
        if not server:
            return False

        item["server"] = server

        # check uuid
        if "uuid" in item and not utils.verify_uuid(item.get("uuid")):
            return False

        if "tfo" in item and item.get("tfo") not in [False, True]:
            return False

        authentication = "password"
        item["port"] = int(item["port"])
        if item["type"] == "ss":
            if item["cipher"] not in SS_SUPPORTED_CIPHERS:
                return False
            # https://github.com/Dreamacro/clash/blob/master/adapter/outbound/shadowsocks.go#L109
            plugin = item.get("plugin", "")
            if plugin not in ["", "obfs", "v2ray-plugin"]:
                return False
            if plugin:
                option = item.get("plugin-opts", {}).get("mode", "")
                if (
                    not option
                    or (plugin == "v2ray-plugin" and option != "websocket")
                    or (plugin == "obfs" and option not in ["tls", "http"])
                ):
                    return False
        elif item["type"] == "ssr":
            if item["cipher"] not in SS_SUPPORTED_CIPHERS:
                return False
            if item["obfs"] not in SSR_SUPPORTED_OBFS:
                return False
            if item["protocol"] not in SSR_SUPPORTED_PROTOCOL:
                return False
        elif item["type"] == "vmess" or item["type"] == "vless":
            authentication = "uuid"
            if "udp" in item and item["udp"] not in [False, True]:
                return False
            if "tls" in item and item["tls"] not in [False, True]:
                return False
            if item.get("network", "ws") in ["h2", "grpc"] and not item.get(
                "tls", False
            ):
                return False
            if "skip-cert-verify" in item and item["skip-cert-verify"] not in [
                False,
                True,
            ]:
                return False
            if item["cipher"] not in VMESS_SUPPORTED_CIPHERS:
                return False

            # https://dreamacro.github.io/clash/zh_CN/configuration/configuration-reference.html
            if "h2-opts" in item:
                h2_opts = item.get("h2-opts", {})
                if not h2_opts or type(h2_opts) != dict:
                    return False
                if "host" in h2_opts and type(h2_opts["host"]) != list:
                    return False
            elif "http-opts" in item:
                http_opts = item.get("http-opts", {})
                if not http_opts or type(http_opts) != dict:
                    return False
                if "path" in http_opts and type(http_opts["path"]) != list:
                    return False
                if "headers" in http_opts and type(http_opts["headers"]) != list:
                    return False
        elif item["type"] == "trojan":
            if "udp" in item and item["udp"] not in [False, True]:
                return False
            if "skip-cert-verify" in item and item["skip-cert-verify"] not in [
                False,
                True,
            ]:
                return False
        elif item["type"] == "snell":
            authentication = "psk"
            if "udp" in item and item["udp"] not in [False, True]:
                return False
            if "skip-cert-verify" in item and item["skip-cert-verify"] not in [
                False,
                True,
            ]:
                return False
        elif item["type"] == "http":
            authentication = "userpass"
            if "tls" in item and item["tls"] not in [False, True]:
                return False
        elif item["type"] == "socks5":
            authentication = "userpass"
            if "tls" in item and item["tls"] not in [False, True]:
                return False
            if "udp" in item and item["udp"] not in [False, True]:
                return False
            if "skip-cert-verify" in item and item["skip-cert-verify"] not in [
                False,
                True,
            ]:
                return False
        else:
            return False

        if not item[authentication] or utils.is_number(item[authentication]):
            return False

        return True
    except:
        return False


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
        alive, allowed = True, False
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
            if proxy.pop("chatgpt", False) and not proxy_name.endswith(
                utils.CHATGPT_FLAG
            ):
                try:
                    # check for ChatGPT Web: https://chat.openai.com
                    request = urllib.request.Request(
                        url=f"{base_url}https://chat.openai.com/favicon.ico&expected=200",
                        headers=utils.DEFAULT_HTTP_HEADERS,
                    )
                    response = urllib.request.urlopen(request, timeout=5, context=CTX)
                    if response.getcode() == 200:
                        content = str(response.read(), encoding="utf-8")
                        data = json.loads(content)
                        allowed = data.get("delay", -1) > 0

                    # check for ChatGPT API: https://api.openai.com
                    if allowed:
                        content = utils.http_get(
                            url=f"{base_url}https://api.openai.com/v1/engines&expected=401",
                            retry=1,
                        )
                        data = json.loads(content)
                        if data.get("delay", -1) > 0:
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
