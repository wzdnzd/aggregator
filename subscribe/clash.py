# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import base64
import itertools
import json
import os
import random
import re
import ssl
import string
import urllib
import urllib.parse
import urllib.request
from collections import defaultdict

import executable
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


class QuotedStr(str):
    pass


def quoted_scalar(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')


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
        # avoid mihomo error: invalid REALITY short ID see: https://github.com/MetaCubeX/mihomo/blob/Meta/adapter/outbound/reality.go#L35
        yaml.add_representer(QuotedStr, quoted_scalar)

        # write to file
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
        if not proxies_exists(item, hosts):
            unique_proxies.append(item)
            key = f"{item.get('server')}:{item.get('port')}"
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
            str(p.get("protocol-param", "")).lower() == str(proxy.get("protocol-param", "")).lower() for p in proxies
        )
    elif protocol == "vmess" or protocol == "vless":
        return any(p.get("uuid", "") == proxy.get("uuid", "") for p in proxies)
    elif protocol == "snell":
        return any(p.get("psk", "") == proxy.get("psk", "") for p in proxies)
    elif protocol == "tuic":
        if proxy.get("token", ""):
            return any(p.get("token", "") == proxy.get("token", "") for p in proxies)
        return any(p.get("uuid", "") == proxy.get("uuid", "") for p in proxies)
    elif protocol == "hysteria2":
        return any(p.get("password", "") == proxy.get("password", "") for p in proxies)
    elif protocol == "hysteria":
        key = "auth-str" if "auth-str" in proxy else "auth_str"
        value = proxy.get(key, "")
        for p in proxies:
            if "auth-str" in p and p.get("auth-str", "") == value:
                return True
            if "auth_str" in p and p.get("auth_str", "") == value:
                return True

    return False


COMMON_SS_SUPPORTED_CIPHERS = [
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

# reference: https://github.com/MetaCubeX/sing-shadowsocks2/blob/dev/shadowaead_2022/method.go#L73-L86
MIHOMO_SS_SUPPORTED_CIPHERS_SALT_LEN = {
    "2022-blake3-aes-128-gcm": 16,
    "2022-blake3-aes-256-gcm": 32,
    "2022-blake3-chacha20-poly1305": 32,
}

MIHOMO_SS_SUPPORTED_CIPHERS = (
    COMMON_SS_SUPPORTED_CIPHERS
    + list(MIHOMO_SS_SUPPORTED_CIPHERS_SALT_LEN.keys())
    + [
        "aes-128-ccm",
        "aes-192-ccm",
        "aes-256-ccm",
        "aes-128-gcm-siv",
        "aes-256-gcm-siv",
        "chacha20",
        "chacha8-ietf-poly1305",
        "xchacha8-ietf-poly1305",
        "lea-128-gcm",
        "lea-192-gcm",
        "lea-256-gcm",
        "rabbit128-poly1305",
        "aegis-128l",
        "aegis-256",
        "aez-384",
        "deoxys-ii-256-128",
        "none",
    ]
)

SSR_SUPPORTED_CIPHERS = COMMON_SS_SUPPORTED_CIPHERS + ["dummy", "none"]

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

SPECIAL_PROTOCOLS = set(["vless", "tuic", "hysteria", "hysteria2"])

# xtls-rprx-direct and xtls-rprx-origin are deprecated and no longer supported
# XTLS_FLOWS = set(["xtls-rprx-direct", "xtls-rprx-origin", "xtls-rprx-vision"])


def is_hex(word: str) -> bool:
    digits = set("0123456789abcdef")
    word = word.lower().strip()
    for c in word:
        if not (c in digits):
            return False

    return True


def check_ports(port: str, ranges: str, protocol: str) -> bool:
    protocol = utils.trim(protocol).lower()

    try:
        flag = 0 < int(port) <= 65535
        if not flag or protocol not in ["hysteria", "hysteria2"] or not ranges:
            return flag
    except:
        return False

    nums = re.split(r"/|,", utils.trim(ranges))
    if not nums:
        return False

    for num in nums:
        start, end = num, num
        if "-" in num:
            start, end = num.split("-", maxsplit=1)

        try:
            start, end = int(start), int(end)
            if start <= 0 or start > 65535 or end <= 0 or end > 65535 or start > end:
                return False
        except:
            return False

    return True


def verify(item: dict, mihomo: bool = True) -> bool:
    if not item or type(item) != dict or "type" not in item:
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

        # port must be valid port number
        if not check_ports(item.get("port", ""), item.get("ports", None), item.get("type", "")):
            return False

        # check uuid
        if "uuid" in item and not utils.verify_uuid(item.get("uuid")):
            return False

        # check servername and sni
        for attribute in ["servername", "sni"]:
            if attribute in item and type(item[attribute]) != str:
                return False

        for attribute in ["udp", "tls", "skip-cert-verify", "tfo"]:
            if attribute in item and item[attribute] not in [False, True]:
                return False

        authentication = "password"

        if item["type"] == "ss":
            ciphers = COMMON_SS_SUPPORTED_CIPHERS if not mihomo else MIHOMO_SS_SUPPORTED_CIPHERS
            if item["cipher"] not in ciphers:
                return False

            if item["cipher"] in MIHOMO_SS_SUPPORTED_CIPHERS_SALT_LEN:
                # will throw bad key length error
                # see: https://github.com/MetaCubeX/sing-shadowsocks2/blob/dev/shadowaead_2022/method.go#L59-L108
                password = str(item.get(authentication, ""))
                words = password.split(":")
                for word in words:
                    try:
                        text = base64.b64decode(word)
                        if len(text) != MIHOMO_SS_SUPPORTED_CIPHERS_SALT_LEN.get(item["cipher"]):
                            return False
                    except:
                        return False

            plugin = item.get("plugin", "")

            # clash: https://clash.wiki/configuration/outbound.html#shadowsocks
            # mihomo: https://wiki.metacubex.one/config/proxies/ss/#plugin
            all_plugins, meta_plugins = ["", "obfs", "v2ray-plugin"], ["shadow-tls", "restls"]
            if mihomo:
                all_plugins.extend(meta_plugins)

            if plugin not in all_plugins:
                return False
            if plugin:
                option = item.get("plugin-opts", {}).get("mode", "")
                if plugin not in meta_plugins and (
                    not option
                    or (plugin == "v2ray-plugin" and option != "websocket")
                    or (plugin == "obfs" and option not in ["tls", "http"])
                ):
                    return False
        elif item["type"] == "ssr":
            if item["cipher"] not in SSR_SUPPORTED_CIPHERS:
                return False
            if item["obfs"] not in SSR_SUPPORTED_OBFS:
                return False
            if item["protocol"] not in SSR_SUPPORTED_PROTOCOL:
                return False
        elif item["type"] == "vmess":
            authentication = "uuid"

            # clash: https://clash.wiki/configuration/outbound.html#vmess
            # mihomo: https://wiki.metacubex.one/config/proxies/vmess/#network
            network, network_opts = item.get("network", "ws"), ["ws", "h2", "http", "grpc"]
            if mihomo:
                network_opts.append("httpupgrade")

            if network not in network_opts:
                return False
            if item.get("network", "ws") in ["h2", "grpc"] and not item.get("tls", False):
                return False

            # mihomo: https://wiki.metacubex.one/config/proxies/vmess/#cipher
            ciphers = VMESS_SUPPORTED_CIPHERS + ["zero"] if mihomo else VMESS_SUPPORTED_CIPHERS
            if item["cipher"] not in ciphers:
                return False
            if "alterId" not in item or not utils.is_number(item["alterId"]):
                return False

            if "h2-opts" in item:
                if network != "h2":
                    return False

                h2_opts = item.get("h2-opts", {})
                if not h2_opts or type(h2_opts) != dict:
                    return False
                if "host" in h2_opts and type(h2_opts["host"]) != list:
                    return False
            elif "http-opts" in item:
                if network != "http":
                    return False

                http_opts = item.get("http-opts", {})
                if not http_opts or type(http_opts) != dict:
                    return False
                if "path" in http_opts and type(http_opts["path"]) != list:
                    return False
                if "headers" in http_opts:
                    headers = http_opts.get("headers", {})
                    if not isinstance(headers, dict):
                        return False

                    for key, value in headers.items():
                        if not isinstance(key, str):
                            return False
                        if key.lower() == "host" and not isinstance(value, list):
                            return False
            elif "ws-opts" in item:
                if network != "ws" and network != "httpupgrade":
                    return False

                ws_opts = item.get("ws-opts", {})
                if not ws_opts or type(ws_opts) != dict:
                    return False
                if "path" in ws_opts and type(ws_opts["path"]) != str:
                    return False
                if "headers" in ws_opts and type(ws_opts["headers"]) != dict:
                    return False
            elif "grpc-opts" in item:
                if network != "grpc":
                    return False
                if not mihomo:
                    return False

                grpc_opts = item.get("grpc-opts", {})
                if not grpc_opts or type(grpc_opts) != dict:
                    return False
                if "grpc-service-name" not in grpc_opts or type(grpc_opts["grpc-service-name"]) != str:
                    return False
        elif item["type"] == "trojan":
            network = utils.trim(item.get("network", ""))

            if "alpn" in item and type(item["alpn"]) != list:
                return False
            if "ws-opts" in item:
                if network != "ws":
                    return False

                ws_opts = item.get("ws-opts", {})
                if not ws_opts or type(ws_opts) != dict:
                    return False
                if "path" in ws_opts and type(ws_opts["path"]) != str:
                    return False
                if "headers" in ws_opts and type(ws_opts["headers"]) != dict:
                    return False
            if "grpc-opts" in item:
                if network != "grpc":
                    return False

                grpc_opts = item.get("grpc-opts", {})
                if not grpc_opts or type(grpc_opts) != dict:
                    return False
                if "grpc-service-name" not in grpc_opts or type(grpc_opts["grpc-service-name"]) != str:
                    return False
            if "flow" in item and (not mihomo or item["flow"] not in ["xtls-rprx-origin", "xtls-rprx-direct"]):
                return False
        elif item["type"] == "snell":
            authentication = "psk"
            if "version" in item and not item["version"].isdigit():
                return False

            version = int(item.get("version", 1))
            if version < 1 or version > 3:
                return False
            if version != 3:
                # only version 3 supports UDP
                item.pop("udp", None)

            if "obfs-opts" in item:
                obfs_opts = item.get("obfs-opts", {})
                if not obfs_opts or type(obfs_opts) != dict:
                    return False
                if "mode" in obfs_opts:
                    mode = utils.trim(obfs_opts.get("mode", ""))
                    if mode not in ["http", "tls"]:
                        return False
        elif item["type"] == "http" or item["type"] == "socks5":
            authentication = "userpass"
        elif mihomo and item["type"] in SPECIAL_PROTOCOLS:
            if item["type"] == "vless":
                authentication = "uuid"
                network = utils.trim(item.get("network", "tcp"))

                # mihomo: https://wiki.metacubex.one/config/proxies/vless/#network
                network_opts = ["ws", "tcp", "grpc", "http", "h2"] if mihomo else ["ws", "tcp", "grpc"]

                if network not in network_opts:
                    return False
                if "flow" in item:
                    flow = utils.trim(item.get("flow", ""))

                    # if flow and flow not in XTLS_FLOWS:
                    if flow and flow != "xtls-rprx-vision":
                        return False
                if "ws-opts" in item:
                    if network != "ws":
                        return False

                    ws_opts = item.get("ws-opts", {})
                    if not ws_opts or type(ws_opts) != dict:
                        return False
                    if "path" in ws_opts and type(ws_opts["path"]) != str:
                        return False
                    if "headers" in ws_opts and type(ws_opts["headers"]) != dict:
                        return False
                if "grpc-opts" in item:
                    if network != "grpc":
                        return False

                    grpc_opts = item.get("grpc-opts", {})
                    if not grpc_opts or type(grpc_opts) != dict:
                        return False
                    if "grpc-service-name" not in grpc_opts or type(grpc_opts["grpc-service-name"]) != str:
                        return False
                if "reality-opts" in item:
                    reality_opts = item.get("reality-opts", {})
                    if not reality_opts or type(reality_opts) != dict:
                        return False
                    if "public-key" not in reality_opts or type(reality_opts["public-key"]) != str:
                        return False
                    if "short-id" in reality_opts:
                        short_id = reality_opts["short-id"]
                        if type(short_id) != str:
                            if utils.is_number(short_id):
                                short_id = str(short_id)
                            else:
                                return False

                        if len(short_id) != 8 or not is_hex(short_id):
                            return False

                        reality_opts["short-id"] = QuotedStr(short_id)
            elif item["type"] == "tuic":
                # mihomo: https://wiki.metacubex.one/config/proxies/tuic
                token = wrap(item.get("token", ""))
                uuid = wrap(item.get("uuid", ""))
                password = wrap(item.get("password", ""))
                if not token and not uuid and not password:
                    return False
                if token and uuid and password:
                    return False
                if token:
                    authentication = "token"
                    item["token"] = token
                else:
                    if not uuid:
                        return False

                    authentication = "uuid"
                    if password:
                        item["password"] = password

                for property in ["disable-sni", "reduce-rtt", "fast-open"]:
                    if property in item and item[property] not in [False, True]:
                        return False
                for property in [
                    "heartbeat-interval",
                    "request-timeout",
                    "max-udp-relay-packet-size",
                    "max-open-streams",
                ]:
                    if property in item and not utils.is_number(item[property]):
                        return False
                if "udp-relay-mode" in item and item["udp-relay-mode"] not in ["native", "quic"]:
                    return False
                if "congestion-controller" in item and item["congestion-controller"] not in [
                    "cubic",
                    "bbr",
                    "new_reno",
                ]:
                    return False
                if "alpn" in item and type(item["alpn"]) != list:
                    return False
                if "ip" in item:
                    ip = utils.trim(item.get("ip", ""))

                    # ip must be valid ipv4 or ipv6 address
                    if not re.match(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$", ip) and not re.match(
                        r"^(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$", ip
                    ):
                        return False
            else:
                for property in ["up", "down"]:
                    if property not in item:
                        continue

                    traffic = item.get(property, "")
                    if traffic and utils.is_number(traffic):
                        traffic = str(traffic)

                    if not re.match(r"^\d+(\.\d+)?(\s+)?([kmgt]?bps)?$", utils.trim(traffic), flags=re.I):
                        return False

                if "alpn" in item and type(item["alpn"]) != list:
                    return False
                for property in ["ca", "ca-str"]:
                    if property in item and type(item[property]) != str:
                        return False
                if item["type"] == "hysteria2":
                    # mihomo: https://wiki.metacubex.one/config/proxies/hysteria2
                    authentication = "password"
                    if "obfs" in item:
                        obfs = utils.trim(item.get("obfs", ""))
                        if obfs != "salamander":
                            return False
                    if "obfs-password" in item and type(item["obfs-password"]) != str:
                        return False
                else:
                    # mihomo: https://wiki.metacubex.one/config/proxies/hysteria
                    authentication = "auth-str" if "auth-str" in item else "auth_str"

                    for property in ["auth-str", "auth_str", "obfs"]:
                        if property in item and type(item[property]) != str:
                            return False
                    for property in ["disable_mtu_discovery", "fast-open"]:
                        if property in item and item[property] not in [False, True]:
                            return False
                    if "protocol" in item:
                        protocol = utils.trim(item.get("protocol", ""))
                        if protocol not in ["udp", "wechat-video", "faketcp"]:
                            return False
                    if "ports" in item:
                        ports = utils.trim(item.get("ports", [])).split(",")
                        if not ports:
                            return False
                        for port in ports:
                            # port must be valid port number
                            if not utils.is_number(port) or int(port) <= 0 or int(port) > 65535:
                                return False
                    for property in ["recv_window_conn", "recv-window-conn", "recv_window", "recv-window"]:
                        if property not in item:
                            continue
                        window = item.get(property, "")
                        if not utils.is_number(window):
                            return False
        else:
            return False

        if not item.get(authentication, ""):
            return False

        if utils.is_number(item[authentication]):
            item[authentication] = QuotedStr(item[authentication])

        return True
    except:
        return False


def check(proxy: dict, api_url: str, timeout: int, test_url: str, delay: int, strict: bool = False) -> bool:
    proxy_name = ""
    try:
        proxy_name = urllib.parse.quote(proxy.get("name", ""))
    except:
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
            if proxy.pop("chatgpt", False) and not proxy_name.endswith(utils.CHATGPT_FLAG):
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

        return alive
    except:
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


def wrap(text: str) -> str:
    if utils.is_number(text):
        text = str(text)

    return utils.trim(text)
