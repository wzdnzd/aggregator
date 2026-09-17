# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-07-12

import gzip
import http.client
import json
import math
import os
import random
import re
import socket
import ssl
import subprocess
import time
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass
from functools import partial
from typing import Optional

import utils
import yaml
from executable import which_bin
from geoip2 import database
from iplibrary import create_library, get_providers, resolve_egress_ipv4
from logger import logger

from clash import is_mihomo


@dataclass
class GeoInfo:
    """Country and CDN attributes of an IP"""

    country: str = ""
    is_cdn: bool = False


@dataclass
class ProxyInfo(GeoInfo):
    """Proxy query result, including geo attributes"""

    name: str = ""
    ip_type: str = ""
    score: Optional[int] = None
    provider: str = ""


@dataclass
class ProxyQueryResult:
    """Complete proxy query result"""

    proxy: dict[str, object]
    result: ProxyInfo
    success: bool


# Mapping from ISO country codes to Chinese country names
ISO_TO_CHINESE = {
    "AD": "安道尔",
    "AE": "阿联酋",
    "AF": "阿富汗",
    "AG": "安提瓜和巴布达",
    "AI": "安圭拉",
    "AL": "阿尔巴尼亚",
    "AM": "亚美尼亚",
    "AO": "安哥拉",
    "AR": "阿根廷",
    "AS": "美属萨摩亚",
    "AT": "奥地利",
    "AU": "澳大利亚",
    "AW": "阿鲁巴",
    "AX": "奥兰群岛",
    "AZ": "阿塞拜疆",
    "BA": "波黑",
    "BB": "巴巴多斯",
    "BD": "孟加拉国",
    "BE": "比利时",
    "BF": "布基纳法索",
    "BG": "保加利亚",
    "BH": "巴林",
    "BI": "布隆迪",
    "BJ": "贝宁",
    "BL": "圣巴泰勒米",
    "BM": "百慕大",
    "BN": "文莱",
    "BO": "玻利维亚",
    "BQ": "荷兰加勒比区",
    "BR": "巴西",
    "BS": "巴哈马",
    "BT": "不丹",
    "BV": "布韦岛",
    "BW": "博茨瓦纳",
    "BY": "白俄罗斯",
    "BZ": "伯利兹",
    "CA": "加拿大",
    "CC": "科科斯群岛",
    "CD": "刚果民主共和国",
    "CF": "中非",
    "CG": "刚果共和国",
    "CH": "瑞士",
    "CI": "科特迪瓦",
    "CK": "库克群岛",
    "CL": "智利",
    "CM": "喀麦隆",
    "CN": "中国",
    "CO": "哥伦比亚",
    "CR": "哥斯达黎加",
    "CU": "古巴",
    "CV": "佛得角",
    "CW": "库拉索",
    "CX": "圣诞岛",
    "CY": "塞浦路斯",
    "CZ": "捷克",
    "DE": "德国",
    "DJ": "吉布提",
    "DK": "丹麦",
    "DM": "多米尼克",
    "DO": "多米尼加",
    "DZ": "阿尔及利亚",
    "EC": "厄瓜多尔",
    "EE": "爱沙尼亚",
    "EG": "埃及",
    "EH": "西撒哈拉",
    "ER": "厄立特里亚",
    "ES": "西班牙",
    "ET": "埃塞俄比亚",
    "FI": "芬兰",
    "FJ": "斐济",
    "FK": "福克兰群岛",
    "FM": "密克罗尼西亚",
    "FO": "法罗群岛",
    "FR": "法国",
    "GA": "加蓬",
    "GB": "英国",
    "GD": "格林纳达",
    "GE": "格鲁吉亚",
    "GF": "法属圭亚那",
    "GG": "根西岛",
    "GH": "加纳",
    "GI": "直布罗陀",
    "GL": "格陵兰",
    "GM": "冈比亚",
    "GN": "几内亚",
    "GP": "瓜德罗普",
    "GQ": "赤道几内亚",
    "GR": "希腊",
    "GS": "南乔治亚和南桑威奇群岛",
    "GT": "危地马拉",
    "GU": "关岛",
    "GW": "几内亚比绍",
    "GY": "圭亚那",
    "HK": "香港",
    "HM": "赫德岛和麦克唐纳群岛",
    "HN": "洪都拉斯",
    "HR": "克罗地亚",
    "HT": "海地",
    "HU": "匈牙利",
    "ID": "印度尼西亚",
    "IE": "爱尔兰",
    "IL": "以色列",
    "IM": "马恩岛",
    "IN": "印度",
    "IO": "英属印度洋领地",
    "IQ": "伊拉克",
    "IR": "伊朗",
    "IS": "冰岛",
    "IT": "意大利",
    "JE": "泽西岛",
    "JM": "牙买加",
    "JO": "约旦",
    "JP": "日本",
    "KE": "肯尼亚",
    "KG": "吉尔吉斯斯坦",
    "KH": "柬埔寨",
    "KI": "基里巴斯",
    "KM": "科摩罗",
    "KN": "圣基茨和尼维斯",
    "KP": "朝鲜",
    "KR": "韩国",
    "KW": "科威特",
    "KY": "开曼群岛",
    "KZ": "哈萨克斯坦",
    "LA": "老挝",
    "LB": "黎巴嫩",
    "LC": "圣卢西亚",
    "LI": "列支敦士登",
    "LK": "斯里兰卡",
    "LR": "利比里亚",
    "LS": "莱索托",
    "LT": "立陶宛",
    "LU": "卢森堡",
    "LV": "拉脱维亚",
    "LY": "利比亚",
    "MA": "摩洛哥",
    "MC": "摩纳哥",
    "MD": "摩尔多瓦",
    "ME": "黑山",
    "MF": "法属圣马丁",
    "MG": "马达加斯加",
    "MH": "马绍尔群岛",
    "MK": "北马其顿",
    "ML": "马里",
    "MM": "缅甸",
    "MN": "蒙古",
    "MO": "澳门",
    "MP": "北马里亚纳群岛",
    "MQ": "马提尼克",
    "MR": "毛里塔尼亚",
    "MS": "蒙特塞拉特",
    "MT": "马耳他",
    "MU": "毛里求斯",
    "MV": "马尔代夫",
    "MW": "马拉维",
    "MX": "墨西哥",
    "MY": "马来西亚",
    "MZ": "莫桑比克",
    "NA": "纳米比亚",
    "NC": "新喀里多尼亚",
    "NE": "尼日尔",
    "NF": "诺福克岛",
    "NG": "尼日利亚",
    "NI": "尼加拉瓜",
    "NL": "荷兰",
    "NO": "挪威",
    "NP": "尼泊尔",
    "NR": "瑙鲁",
    "NU": "纽埃",
    "NZ": "新西兰",
    "OM": "阿曼",
    "PA": "巴拿马",
    "PE": "秘鲁",
    "PF": "法属波利尼西亚",
    "PG": "巴布亚新几内亚",
    "PH": "菲律宾",
    "PK": "巴基斯坦",
    "PL": "波兰",
    "PM": "圣皮埃尔和密克隆",
    "PN": "皮特凯恩群岛",
    "PR": "波多黎各",
    "PS": "巴勒斯坦",
    "PT": "葡萄牙",
    "PW": "帕劳",
    "PY": "巴拉圭",
    "QA": "卡塔尔",
    "RE": "留尼汪",
    "RO": "罗马尼亚",
    "RS": "塞尔维亚",
    "RU": "俄罗斯",
    "RW": "卢旺达",
    "SA": "沙特阿拉伯",
    "SB": "所罗门群岛",
    "SC": "塞舌尔",
    "SD": "苏丹",
    "SE": "瑞典",
    "SG": "新加坡",
    "SH": "圣赫勒拿",
    "SI": "斯洛文尼亚",
    "SJ": "斯瓦尔巴和扬马延",
    "SK": "斯洛伐克",
    "SL": "塞拉利昂",
    "SM": "圣马力诺",
    "SN": "塞内加尔",
    "SO": "索马里",
    "SR": "苏里南",
    "SS": "南苏丹",
    "ST": "圣多美和普林西比",
    "SV": "萨尔瓦多",
    "SX": "荷属圣马丁",
    "SY": "叙利亚",
    "SZ": "斯威士兰",
    "TC": "特克斯和凯科斯群岛",
    "TD": "乍得",
    "TF": "法属南部领地",
    "TG": "多哥",
    "TH": "泰国",
    "TJ": "塔吉克斯坦",
    "TK": "托克劳",
    "TL": "东帝汶",
    "TM": "土库曼斯坦",
    "TN": "突尼斯",
    "TO": "汤加",
    "TR": "土耳其",
    "TT": "特立尼达和多巴哥",
    "TV": "图瓦卢",
    "TW": "台湾",
    "TZ": "坦桑尼亚",
    "UA": "乌克兰",
    "UG": "乌干达",
    "UM": "美国本土外小岛屿",
    "US": "美国",
    "UY": "乌拉圭",
    "UZ": "乌兹别克斯坦",
    "VA": "梵蒂冈",
    "VC": "圣文森特和格林纳丁斯",
    "VE": "委内瑞拉",
    "VG": "英属维尔京群岛",
    "VI": "美属维尔京群岛",
    "VN": "越南",
    "VU": "瓦努阿图",
    "WF": "瓦利斯和富图纳",
    "WS": "萨摩亚",
    "YE": "也门",
    "YT": "马约特",
    "ZA": "南非",
    "ZM": "赞比亚",
    "ZW": "津巴布韦",
}


# Pattern for CDN providers and Loyalsoldier custom ISO codes
CDN_PATTERN = r"cloudflare|cloudfront|fastly|google"
_CDN_NAME_RE = re.compile(CDN_PATTERN, flags=re.I)


def is_cdn_label(value: str) -> bool:
    """Return True if a country name or ISO code refers to a CDN instead of a location"""
    text = utils.trim(value)
    return bool(text and _CDN_NAME_RE.search(text))


def _mark_cdn(proxy: dict[str, object]) -> None:
    if isinstance(proxy, dict):
        proxy["cdn"] = True


def _is_cdn_proxy(proxy: dict[str, object]) -> bool:
    return isinstance(proxy, dict) and (bool(proxy.get("cdn")) or is_cdn_label(str(proxy.get("name", ""))))


def _remove_temp_flags(proxies: list[dict]) -> list[dict]:
    for proxy in proxies:
        if isinstance(proxy, dict):
            proxy.pop("cdn", None)
            proxy.pop("renamed", None)
    return proxies


def download_mmdb(repo: str, target: str, filepath: str, retry: int = 3) -> bool:
    """
    Download GeoLite2-City.mmdb from github release
    """
    repo = utils.trim(text=repo)
    if not repo or len(repo.split("/", maxsplit=1)) != 2:
        logger.error(f"invalid github repo name: {repo}")
        return False

    target = utils.trim(text=target)
    if not target:
        logger.error("invalid download target")
        return False

    # extract download url from github release page
    release_api = f"https://api.github.com/repos/{repo}/releases/latest?per_page=1"

    assets, content = None, utils.http_get(url=release_api)
    try:
        data = json.loads(content)
        assets = data.get("assets", [])
    except:
        logger.error(f"failed download {target} due to cannot extract download url through Github API")

    if not assets or not isinstance(assets, list):
        logger.error(f"no assets found for {target} in github release")
        return False

    download_url = ""
    for asset in assets:
        if asset.get("name", "") == target:
            download_url = asset.get("browser_download_url", "")
            break

    if not download_url:
        logger.error(f"no download url found for {target} in github release")
        return False

    return download(download_url, filepath, target, retry)


def download(url: str, filepath: str, filename: str, retry: int = 3) -> bool:
    """Download file from url to filepath with filename"""

    if retry < 0:
        logger.error(f"archieved max retry count for download, url: {url}")
        return False

    url = utils.trim(text=url)
    if not url:
        logger.error("invalid download url")
        return False

    filepath = utils.trim(text=filepath)
    if not filepath:
        logger.error(f"invalid save filepath, url: {url}")
        return False

    filename = utils.trim(text=filename)
    if not filename:
        logger.error(f"invalid save filename, url: {url}")
        return False

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

    logger.info(f"download file {filename} to {fullpath} success")
    return True


def load_mmdb(
    directory: str, repo: str = "Loyalsoldier/geoip", filename: str = "Country.mmdb", update: bool = False
) -> database.Reader:
    filepath = os.path.join(directory, filename)
    if update or not os.path.exists(filepath) or not os.path.isfile(filepath):
        if not download_mmdb(repo, filename, directory):
            return None

    return database.Reader(filepath)


def lookup_ip_geo(ip: str, reader: database.Reader) -> GeoInfo:
    """
    Query country information for an IP address using mmdb database

    CDN ranges such as Cloudflare are reported via is_cdn and never as a country
    """
    if not ip or not reader:
        return GeoInfo()

    try:
        # fake ip
        if ip.startswith("198.18.0."):
            logger.warning("cannot get geolocation because IP address is faked")
            return GeoInfo()

        response = reader.country(ip)
        names = response.country.names or {}
        iso_code = utils.trim(response.country.iso_code).upper()
        country = utils.trim(names.get("zh-CN", ""))

        if not country and iso_code:
            country = ISO_TO_CHINESE.get(iso_code, iso_code)

        well_known_cdn = ip in ("1.1.1.1", "1.0.0.1") or ip.startswith("8.8.8.") or ip.startswith("8.8.4.")
        if well_known_cdn or is_cdn_label(iso_code) or is_cdn_label(country):
            return GeoInfo(is_cdn=True)

        return GeoInfo(country=country)
    except Exception as e:
        logger.error(f"query ip country failed, ip: {ip}, error: {str(e)}")
        return GeoInfo()


def query_ip_country(ip: str, reader: database.Reader) -> str:
    """
    Query country information for an IP address using mmdb database

    Args:
        ip: The IP address to query
        reader: The mmdb database reader

    Returns:
        The country name in Chinese
    """
    return lookup_ip_geo(ip, reader).country


def locate_by_geoip(proxy: dict[str, object], reader: database.Reader) -> dict[str, object]:
    if not proxy or not isinstance(proxy, dict):
        return None

    address = utils.trim(proxy.get("server", ""))
    if not address:
        logger.warning(f"server is empty, proxy: {proxy}")
        return proxy

    try:
        if reader is None:
            logger.error("MMDB reader is None, cannot query geolocation")
            return proxy

        ip = socket.gethostbyname(address)
        geo = lookup_ip_geo(ip, reader)
        if geo.is_cdn:
            _mark_cdn(proxy)
            logger.debug(f"server IP belongs to CDN, skip as location, address: {address}")
        elif geo.country:
            proxy["name"] = geo.country
            proxy["renamed"] = True
        else:
            logger.warning(f"cannot get geolocation and name, address: {address}")
    except Exception as e:
        logger.error(f"query ip geolocation failed, address: {address}, error: {str(e)}")

    return proxy


class PortReservation:
    """Reserve local TCP ports by binding them without listen/connect."""

    def __init__(self) -> None:
        self._sockets = []

    def reserve(self, n: int) -> list[int]:
        if n <= 0:
            return []

        ports = []
        try:
            for _ in range(n):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.bind(("127.0.0.1", 0))
                self._sockets.append(sock)
                ports.append(sock.getsockname()[1])
            return ports
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        sockets, self._sockets = self._sockets, []
        for sock in sockets:
            try:
                sock.close()
            except Exception:
                pass


def generate_mihomo_config(proxies: list[dict], listener_ports: list[int], mixed_port: int) -> tuple[dict, dict]:
    """Generate mihomo configuration for the given proxies"""
    config = {
        "mixed-port": mixed_port,
        "allow-lan": True,
        "mode": "global",
        "log-level": "error",
        "ipv6": False,
        "tcp-concurrent": True,
        "proxies": proxies,
        "dns": {
            "enable": True,
            "ipv6": False,
            "enhanced-mode": "redir-host",
            "default-nameserver": ["114.114.114.114", "223.5.5.5", "8.8.8.8"],
            "nameserver": ["114.114.114.114", "8.8.8.8"],
        },
        "listeners": [],
    }

    records = dict()
    if not proxies:
        return config, records

    for index, proxy in enumerate(proxies):
        if index >= len(listener_ports):
            logger.warning(f"No reserved port for proxy {proxy['name']}")
            continue

        port = listener_ports[index]
        listener = {
            "name": f"http-{index}",
            "type": "http",
            "port": port,
            "proxy": proxy["name"],
            "listen": "127.0.0.1",
            "users": [],
        }
        config["listeners"].append(listener)
        records[proxy["name"]] = port

    return config, records


def _idna_host(host: str) -> str:
    host = utils.trim(host)
    if not host:
        return host
    try:
        return host.encode("idna").decode("ascii")
    except Exception:
        return host


def _origin_headers(url: str, extra: dict[str, str] | None = None) -> dict[str, object]:
    parsed = urllib.parse.urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    result = {
        "User-Agent": utils.USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "close",
        "Referer": f"{base}/" if base else url,
        "Origin": base if base else url,
    }
    if extra and isinstance(extra, dict):
        for key, value in extra.items():
            name = utils.trim(str(key))
            if not name:
                continue
            if value is None:
                result.pop(name, None)
            else:
                result[name] = value
    return result


def _proxy_ssl_context() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.options |= ssl.OP_NO_TICKET
    if hasattr(ssl, "OP_IGNORE_UNEXPECTED_EOF"):
        ctx.options |= ssl.OP_IGNORE_UNEXPECTED_EOF
    try:
        ctx.set_alpn_protocols(["http/1.1"])
    except Exception:
        pass
    return ctx


def _recv_until(sock: socket.socket, marker: bytes, limit: int = 65536) -> bytes:
    buf = bytearray()
    while marker not in buf:
        chunk = sock.recv(min(4096, max(1, limit - len(buf))))
        if not chunk:
            raise OSError(f"tunnel: incomplete proxy response: {bytes(buf)!r}")
        buf += chunk
        if len(buf) > limit:
            raise OSError("tunnel: proxy response too large")
    index = buf.find(marker) + len(marker)
    if index < len(buf):
        raise OSError("tunnel: unexpected data after CONNECT")
    return bytes(buf[:index])


def _tls_server_hostname(host: str) -> Optional[str]:
    text = _idna_host(host)
    if not text:
        return None
    try:
        socket.inet_pton(socket.AF_INET, text)
        return None
    except OSError:
        pass
    if ":" in text:
        try:
            socket.inet_pton(socket.AF_INET6, text.strip("[]"))
            return None
        except OSError:
            pass
    return text


def _open_http_tunnel(sock: socket.socket, host: str, port: int) -> None:
    host = _idna_host(host)
    target = f"{host}:{port}"
    # Do not send Connection/Proxy-Connection: close. Mihomo hijacks after 200;
    # a close flag makes Windows RST the socket (WinError 10054) at TLS.
    sock.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode("ascii"))
    head = _recv_until(sock, b"\r\n\r\n")
    status_line = head.split(b"\r\n", 1)[0].decode("iso-8859-1", "replace")
    parts = status_line.split(" ", 2)
    if len(parts) < 2:
        raise OSError(f"tunnel: invalid CONNECT response: {status_line}")
    try:
        code = int(parts[1])
    except ValueError as e:
        raise OSError(f"tunnel: invalid CONNECT status: {status_line}") from e
    if code != 200:
        raise OSError(f"tunnel: CONNECT failed: {status_line}")


def _assert_tunnel_open(sock: socket.socket, wait: float = 0.2) -> None:
    """Fail fast if the CONNECT already died; otherwise wait out mihomo's peek."""
    previous = sock.gettimeout()
    sock.settimeout(max(wait, 0.01))
    try:
        peeked = sock.recv(1, socket.MSG_PEEK)
        if not peeked:
            raise OSError("tunnel: closed before TLS")
    except (TimeoutError, socket.timeout):
        return
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
        raise OSError(f"tunnel: closed before TLS ({e})") from e
    finally:
        sock.settimeout(previous)


def _http_get_on_sock(sock: socket.socket, host: str, path: str, headers: dict[str, str]) -> tuple[int, str, bytes]:
    host = _idna_host(host)
    lines = [f"GET {path} HTTP/1.1", f"Host: {host}"]
    sent = {"host"}
    for key, value in (headers or {}).items():
        name = utils.trim(str(key))
        if not name or name.lower() in sent or name.lower().startswith("proxy-"):
            continue
        lines.append(f"{name}: {value}")
        sent.add(name.lower())
    if "connection" not in sent:
        lines.append("Connection: close")

    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
    response = http.client.HTTPResponse(sock, method="GET")
    try:
        response.begin()
        return response.status, utils.trim(response.getheader("Location", "")), response.read()
    finally:
        try:
            response.close()
        except Exception:
            pass


def _decode_body(body: bytes) -> str:
    if not body:
        return ""
    if body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except Exception:
            pass
    for encoding in ("utf-8", "gbk"):
        try:
            return body.decode(encoding)
        except Exception:
            continue
    return body.decode("utf-8", "replace")


def _request_through_proxy(
    port: int, url: str, headers: dict[str, str], timeout: int, redirects: int = 3
) -> tuple[int, bytes]:
    """
    Fetch URL via mihomo HTTP inbound.

    http://  → absolute-form GET (plain HTTP proxy).
    https:// → CONNECT then TLS in Python. Do not send `GET https://...`:
    mihomo handles that with client.Do + TLS on net.Pipe, which races the
    outbound dial and comes back as HTTP 502.
    """
    parsed = urllib.parse.urlparse(url)
    scheme = utils.trim(parsed.scheme).lower()
    host = parsed.hostname
    if not host or scheme not in ("http", "https"):
        raise OSError(f"http: unsupported url: {url}")

    dst_port = parsed.port or (443 if scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    wrapped = None
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(timeout)
        target = sock
        request_path = url
        if scheme == "https":
            _open_http_tunnel(sock, host, dst_port)
            _assert_tunnel_open(sock)
            try:
                wrapped = _proxy_ssl_context().wrap_socket(
                    sock,
                    server_hostname=_tls_server_hostname(host),
                    suppress_ragged_eofs=True,
                )
            except OSError as e:
                raise OSError(f"tls: {e}") from e
            target = wrapped
            request_path = path
        status, location, body = _http_get_on_sock(target, host, request_path, headers)
    finally:
        for item in (wrapped, sock):
            if item is None:
                continue
            try:
                item.close()
            except Exception:
                pass

    if status in (301, 302, 303, 307, 308) and redirects > 0 and location:
        text = urllib.parse.urljoin(url, location)
        if text.lower().startswith("http"):
            return _request_through_proxy(port, text, _origin_headers(text, headers), timeout, redirects - 1)

    return status, body


def make_proxy_request(
    port: int,
    url: str,
    max_retries: int = 5,
    timeout: int = 10,
    headers: dict[str, str] = None,
    deserialize: bool = True,
    quiet: bool = False,
) -> tuple[bool, dict]:
    """
    Make an HTTP request through a proxy and return the response

    Args:
        port: The port of the proxy
        url: The URL to request
        max_retries: Maximum number of retry attempts
        timeout: Timeout for the request in seconds


    Returns:
        A tuple of (success, data) where:
        - success: Whether the request was successful
        - data: The parsed JSON data (empty dict if request failed)
    """
    if not port:
        logger.warning("No port provided for proxy")
        return False, {}

    default_headers = _origin_headers(url, headers)
    attempt, success, data = 0, False, None
    while not success and attempt < max(max_retries, 1):
        try:
            if attempt > 0:
                wait_time = min(2**attempt * random.uniform(0.5, 1.5), 6)
                time.sleep(wait_time)

            status, body = _request_through_proxy(port, url, default_headers, timeout)
            if status != 200:
                raise OSError(f"http: status {status}")
            content = _decode_body(body)
            data = json.loads(content) if deserialize else content
            success = True
        except Exception as e:
            message = f"Attempt {attempt+1} failed to request {url} through proxy port {port}: {str(e)}"
            if quiet or attempt + 1 < max(max_retries, 1):
                logger.debug(message)
            else:
                logger.warning(message)

        attempt += 1

    return success, data


def get_ipv4(port: int, max_retries: int = 5) -> str:
    """Get the egress IPv4 address through a proxy listener."""
    if not port:
        logger.warning("No port provided for proxy")
        return ""

    return resolve_egress_ipv4(port, make_proxy_request, max_retries=max_retries, timeout=10)


def _wait_listener(port: int, process: subprocess.Popen, timeout: int = 20) -> None:
    deadline = time.time() + max(timeout, 1)
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"mihomo exited before becoming ready, code={process.returncode}")
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=1)
            sock.close()
            return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"mihomo listener 127.0.0.1:{port} not ready after {timeout}s")


# Online API services for IP location
LOCATION_API_SERVICES = [
    {"url": "https://ipinfo.io", "country_key": "country"},
    {"url": "https://api.ip2location.io", "country_key": "country_code"},
    {"url": "https://ipwho.is", "country_key": "country_code"},
    {"url": "https://free.freeipapi.com/api/json", "country_key": "countryCode"},
    {"url": "https://api.ip.sb/geoip", "country_key": "country_code"},
]


def random_delay(min_delay: float = 0.01, max_delay: float = 0.5) -> None:
    """Random delay to avoid API rate limiting"""
    time.sleep(random.uniform(min_delay, max_delay))


def check_residential(
    proxy: dict[str, object],
    port: int,
    api_key: str = "",
    ip_library: str = "ipnetcoffee",
    reader: database.Reader = None,
    max_retries: int = 2,
    timeout: int = 12,
) -> ProxyQueryResult:
    """
    Check if a proxy is residential by making a request through it

    Args:
        proxy: The proxy information dict
        port: The port of the proxy
        api_key: Optional API key for ipapi.is. Uses free tier if not provided
        ip_library: IP query provider, supported: ipnetcoffee/meowvps/ippure/ip2location/iplark/ipinfo/ipapi
        reader: Optional mmdb reader used to detect CDN egress IPs
        max_retries: Retry count for provider queries
        timeout: Timeout in seconds for provider queries

    Returns:
        ProxyQueryResult: Complete proxy query result
    """
    name = proxy.get("name", "")
    result = ProxyInfo(name=name)

    if not port:
        logger.warning(f"No port found for proxy {name}")
        return ProxyQueryResult(proxy=proxy, result=result, success=False)

    random_delay()

    try:
        providers = get_providers(ip_library)
        classified, provider = None, ""
        egress_ip = None
        request = partial(make_proxy_request, quiet=True)

        def _cached_egress_ip() -> str:
            nonlocal egress_ip
            if egress_ip is None:
                egress_ip = resolve_egress_ipv4(
                    port,
                    request,
                    max_retries=max_retries,
                    timeout=max(timeout, 15),
                )
                if not egress_ip:
                    logger.debug(f"Failed to get egress IP for proxy {name}")
            return egress_ip

        if reader:
            ip = _cached_egress_ip()
            if ip and lookup_ip_geo(ip, reader).is_cdn:
                result.is_cdn = True
                _mark_cdn(proxy)
                logger.debug(f"Egress IP for proxy {name} belongs to CDN, continue locating")
                return ProxyQueryResult(proxy=proxy, result=result, success=False)

        for idx, item in enumerate(providers):
            library = create_library(item, api_key=api_key)
            ip = _cached_egress_ip() if library.needs_egress_ip else ""
            if library.needs_egress_ip and not ip:
                if idx < len(providers) - 1:
                    fallback = providers[idx + 1]
                    logger.debug(f"Skip {item} for proxy {name}, no egress IP, trying fallback: {fallback}")
                else:
                    logger.debug(f"Skip {item} for proxy {name}, no egress IP")
                continue

            data = library.fetch(port, request, max_retries=max_retries, timeout=timeout, ip=ip)
            if data:
                provider = item
                classified = library.classify(data)
                logger.debug(f"IP info for proxy {name} successfully retrieved, provider: {provider}")
                break

            if idx < len(providers) - 1:
                fallback = providers[idx + 1]
                logger.debug(f"Failed to query {item} for proxy {name}, trying fallback: {fallback}")
            else:
                logger.debug(f"Failed to query {item} for proxy {name}")

        if classified:
            try:
                result.provider = utils.trim(provider)
                country_code = utils.trim(classified.country_code).upper()
                if country_code:
                    result.country = ISO_TO_CHINESE.get(country_code, "")

                if not result.country:
                    raw = classified.raw or {}
                    result.country = utils.trim(
                        raw.get("country_zh", "") or raw.get("country", "") or raw.get("country_name", "")
                    )

                company_type = utils.trim(classified.company_type).lower()
                asn_type = utils.trim(classified.asn_type).lower()
                if company_type == "isp" and asn_type == "isp":
                    result.ip_type = "isp"
                elif company_type in ["business", "isp"] and asn_type in ["business", "isp"]:
                    result.ip_type = "business"

                result.score = classified.score
            except Exception as e:
                logger.error(f"Error parsing response for proxy {name}: {str(e)}")
        else:
            logger.warning(f"Failed to query residential info for proxy {name} with providers: {providers}")

        if is_cdn_label(result.country):
            result.is_cdn = True
            _mark_cdn(proxy)
            logger.debug(f"Residential country for proxy {name} is CDN, continue locating")
            return ProxyQueryResult(proxy=proxy, result=result, success=False)

        flag = result.country != "" or result.ip_type != ""
        return ProxyQueryResult(proxy=proxy, result=result, success=flag)

    except Exception as e:
        logger.error(f"Error querying residential info for {name}: {str(e)}")
        return ProxyQueryResult(proxy=proxy, result=result, success=False)


def locate_by_ipinfo(proxy: dict[str, object], port: int, reader: database.Reader = None) -> ProxyQueryResult:
    """Check the location of a single proxy by making a request through it"""
    name = proxy.get("name", "")

    is_cdn = _is_cdn_proxy(proxy)

    def _failed(reason: str = "") -> ProxyQueryResult:
        if reason:
            logger.warning(f"Location query failed for proxy {name}: {reason}")
        if is_cdn:
            _mark_cdn(proxy)
        return ProxyQueryResult(proxy=proxy, result=ProxyInfo(name=name, is_cdn=is_cdn), success=False)

    def _success(country: str) -> ProxyQueryResult:
        info = ProxyInfo(name=name, country=country)
        return ProxyQueryResult(proxy=proxy, result=info, success=True)

    if not port:
        return _failed("No port specified")

    random_delay()

    try:
        if reader:
            ip = get_ipv4(port=port, max_retries=2)
            geo = lookup_ip_geo(ip, reader) if ip else GeoInfo()
            if geo.is_cdn:
                is_cdn = True
                _mark_cdn(proxy)
                logger.debug(f"Egress IP for proxy {name} belongs to CDN, try online APIs")
            elif geo.country:
                logger.debug(f"Location found via MMDB for proxy {name}: {geo.country}")
                return _success(geo.country)

        retries = 3
        for attempt in range(retries):
            service = random.choice(LOCATION_API_SERVICES)
            success, data = make_proxy_request(port=port, url=service["url"], max_retries=1, timeout=12, quiet=True)
            if success and data:
                code = data.get(service["country_key"], "")
                if code:
                    country = ISO_TO_CHINESE.get(code, code)
                    if is_cdn_label(code) or is_cdn_label(country):
                        is_cdn = True
                        _mark_cdn(proxy)
                        logger.debug(f"API country for proxy {name} is CDN, continue locating")
                    else:
                        logger.debug(f"Location found via API for proxy {name}: {country}")
                        return _success(country)

            if attempt < retries - 1:
                delay = min(2**attempt * random.uniform(1, 2), 6)
                logger.debug(
                    f"API attempt {attempt+1} failed for proxy {name} using {service['url']}, retrying in {delay:.2f}s"
                )
                time.sleep(delay)

        return _failed("Unable to determine location from any source")
    except Exception as e:
        logger.error(f"Unexpected error during location query for {name}: {str(e)}")
        return _failed(f"Exception: {str(e)}")


def batch_query(
    proxies: list[dict],
    func: callable,
    num_threads: int = 0,
    show_progress: bool = True,
    description: str = "Querying",
    digits: int = 2,
) -> list[ProxyQueryResult]:
    """
    Run mihomo to query proxies information using the specified function

    Args:
        proxies: List of proxy configurations
        func: Function to query each proxy (locate_by_ipinfo or check_residential)
        num_threads: Number of threads for parallel processing
        show_progress: Whether to show progress
        description: Description for progress display
        digits: Number of digits for proxy naming

    Returns:
        List of ProxyQueryResult with complete information
    """
    if not proxies:
        return []

    if not is_mihomo():
        return [
            ProxyQueryResult(proxy=proxy, result=ProxyInfo(name=proxy.get("name", "")), success=False)
            for proxy in proxies
        ]

    nodes = rename(proxies, digits, False)
    failed = [ProxyQueryResult(proxy=proxy, result=ProxyInfo(name=proxy["name"]), success=False) for proxy in nodes]

    workspace = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "clash")
    mihomo_bin = os.path.join(workspace, which_bin()[0])
    if not os.path.exists(mihomo_bin) or not os.path.isfile(mihomo_bin):
        logger.error("Mihomo binary not found, skipping proxy check")
        return failed

    utils.chmod(mihomo_bin)

    logger.info(f"Generate clash listeners configuration for {len(nodes)} proxies")
    reservation = PortReservation()
    process = None
    try:
        ports = reservation.reserve(1 + len(nodes))
        mixed_port, listener_ports = ports[0], ports[1:]
        config, records = generate_mihomo_config(nodes, listener_ports, mixed_port)

        config_path = os.path.join(workspace, "config.yaml")
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True)

        logger.info(f"Mihomo configuration saved to {config_path}")
        reservation.close()

        logger.info(f"Starting mihomo with configuration {config_path}")
        process = subprocess.Popen(
            [mihomo_bin, "-d", workspace, "-f", config_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        logger.info("Waiting for mihomo to start...")
        _wait_listener(mixed_port, process)
        if listener_ports:
            _wait_listener(listener_ports[0], process, timeout=10)

        mappings = {proxy["name"]: proxy for proxy in nodes}
        tasks = [(mappings[name], port) for name, port in records.items() if name in mappings]
        results = (
            utils.multi_thread_run(
                func=func,
                tasks=tasks,
                num_threads=num_threads,
                show_progress=show_progress,
                description=description,
            )
            or []
        )

        queried, normalized = set(), []
        for item in results:
            if not item:
                continue
            normalized.append(item)
            queried.add(item.proxy.get("name"))

        for proxy in nodes:
            if proxy["name"] not in queried:
                normalized.append(ProxyQueryResult(proxy=proxy, result=ProxyInfo(name=proxy["name"]), success=False))

        return normalized
    except Exception as e:
        logger.error(f"Error during mihomo check: {str(e)}")
        return failed
    finally:
        reservation.close()
        if process:
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                pass


def process_query_results(
    results: list[ProxyQueryResult], strategy: str, score: bool = False
) -> tuple[list[dict], list[dict]]:
    """
    Process proxy query results

    Args:
        results: List of query results
        strategy: Processing strategy ('residential' or 'location')
        score: Whether to prefix node names with provider and trust score

    Returns:
        tuple: (list of successful proxies, list of failed proxies)
    """
    successes, fails = [], []

    for item in results:
        if not item:
            continue

        country = utils.trim(item.result.country) if item.result else ""
        is_cdn = bool(item.result and item.result.is_cdn) or is_cdn_label(country)
        if is_cdn:
            _mark_cdn(item.proxy)

        if item.success and country and not is_cdn:
            # Copy proxy info to avoid modifying original data
            proxy = item.proxy.copy()

            if strategy == "residential":
                # Residential IP check strategy
                name = country
                if item.result.ip_type == "isp":
                    name += "家宽"
                elif item.result.ip_type == "business":
                    name += "商宽"
            else:
                # Location check or unknown strategy
                name = country

            if score and item.result.score is not None:
                source = utils.trim(item.result.provider).upper()
                if source:
                    name = f"[{source}|{str(item.result.score).zfill(3)}] {name}"

            proxy["name"] = name
            successes.append(proxy)
        else:
            # Failed query proxies
            fails.append(item.proxy)

    return successes, fails


def regularize(
    proxies: list[dict],
    directory: str = "",
    update: bool = False,
    num_threads: int = 0,
    show_progress: bool = True,
    locate: bool = False,
    residential: bool = False,
    ip_library: str = "",
    digits: int = 2,
    score: bool = False,
) -> list[dict]:
    if not proxies or not isinstance(proxies, list):
        return proxies

    # Phase 1: Residential check if necessary
    successes, fails = [], []
    reader = None

    if residential:
        locate = True

    if residential or locate:
        directory = utils.trim(directory)
        if not directory:
            directory = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "data")
        reader = load_mmdb(directory=directory, repo="Loyalsoldier/geoip", filename="Country.mmdb", update=update)
        if not reader:
            logger.error("cannot load mmdb: Country.mmdb")

    if residential:
        logger.info(f"Starting residential check for {len(proxies)} proxies")

        # Get https://api.ipapi.is API key from environment variable
        api_key = utils.trim(os.environ.get("IPAPI_IS_API_KEY", ""))

        # Use mihomo to check for residential proxies
        results = batch_query(
            proxies=proxies,
            func=partial(check_residential, api_key=api_key, ip_library=ip_library, reader=reader),
            num_threads=num_threads,
            show_progress=show_progress,
            description="Checking residential",
            digits=digits,
        )

        # Process residential check results
        successes, fails = process_query_results(results, "residential", score=score)
        logger.info(f"Residential check completed: {len(successes)} successful, {len(fails)} failed")
    else:
        fails = proxies

    # Phase 2: Location check if necessary
    if locate and fails:
        logger.info(f"Starting location check for {len(fails)} proxies")

        unconfirmed = list()
        if reader:
            # Try local mmdb lookup first
            sources = [p for p in fails if p and isinstance(p, dict)]
            tasks = [[p, reader] for p in sources]
            mmdb_results = utils.multi_thread_run(locate_by_geoip, tasks, num_threads, show_progress, "")

            for source, proxy in zip(sources, mmdb_results or []):
                node = proxy if proxy and isinstance(proxy, dict) else source
                name = str(node.get("name", ""))
                cdn = bool(node.get("cdn")) or is_cdn_label(name)
                if cdn:
                    _mark_cdn(node)
                if node.pop("renamed", False) and "中国" not in name and not cdn:
                    successes.append(node)
                else:
                    unconfirmed.append(node)
        else:
            # No mmdb available, treat all as unconfirmed
            unconfirmed = fails

        # For unconfirmed proxies, use online API services to get location info
        if unconfirmed:
            logger.info(f"Using online API services for {len(unconfirmed)} unconfirmed proxies")

            # Use mihomo to check IP locations
            query_results = batch_query(
                proxies=unconfirmed,
                func=partial(locate_by_ipinfo, reader=reader),
                num_threads=num_threads,
                show_progress=show_progress,
                description="Querying location",
                digits=digits,
            )

            # Process location check results and handle CDN proxies
            query_successes, query_fails = process_query_results(query_results, "location", score=score)

            # Add query successes to final results
            successes.extend(query_successes)

            # CDN nodes without a real country fall back to US
            for proxy in query_fails:
                if _is_cdn_proxy(proxy):
                    logger.warning(f"Failed to get location for proxy {proxy['name']}, assume it's in US")
                    proxy["name"] = "美国"

                successes.append(proxy)

        logger.info(f"Location check completed for {len(successes)} total proxies")
    else:
        # No location check needed, add all fails to successes
        successes.extend(fails)

    # Return final results
    return rename(proxies=_remove_temp_flags(successes), digits=digits, shuffle=True)


def rename(proxies: list[dict], digits: int = 2, shuffle: bool = False) -> list[dict]:
    if not proxies or not isinstance(proxies, list):
        return []

    records = defaultdict(list)
    for proxy in proxies:
        name = re.sub(r"-?(\d+|(\d+|\s+|(\d+)?-\d+)[A-Z])$", "", proxy.get("name", "")).strip()
        if not name:
            name = "未知地域"

        proxy["name"] = name
        records[name].append(proxy)

    results = list()
    for name, nodes in records.items():
        if not nodes:
            continue

        n = max(digits, math.floor(math.log10(len(nodes))) + 1)
        for index, node in enumerate(nodes):
            node["name"] = f"{name} {str(index+1).zfill(n)}"
            results.append(node)

    if shuffle:
        for _ in range(3):
            random.shuffle(results)

    return results
