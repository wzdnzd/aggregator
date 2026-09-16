# -*- coding: utf-8 -*-

from __future__ import annotations

import ipaddress
import re

import utils

BOOL_FIELDS = ("udp", "tls", "skip-cert-verify", "tfo", "mptcp")
IP_VERSIONS = ("dual", "ipv4", "ipv6", "ipv4-prefer", "ipv6-prefer")
CONGESTION_CONTROLLERS = ("cubic", "bbr", "new_reno")
BBR_PROFILES = ("", "standard", "conservative", "aggressive")
TRAFFIC_PATTERN = re.compile(r"^\d+(\.\d+)?(\s+)?([kmgt]?bps)?$", re.I)


class QuotedStr(str):
    pass


def quoted_scalar(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')


def wrap(text) -> str:
    if utils.is_number(text):
        text = str(text)
    return utils.trim(text)


def normalize_name(item: dict) -> bool:
    name = str(item.get("name", "")).strip()
    if not name:
        return False
    item["name"] = name
    return True


def normalize_server(item: dict) -> bool:
    server = str(item.get("server", "")).strip().lower()
    if not server:
        return False

    if server.startswith("::"):
        # ipv6 addresses starting with "::" can break yaml loading
        try:
            server = ipaddress.IPv6Address(server).exploded
        except Exception:
            return False

    item["server"] = server
    return True


def check_ports(port, ranges, protocol: str) -> bool:
    protocol = utils.trim(protocol).lower()

    try:
        flag = 0 < int(port) <= 65535
        if not flag or protocol not in ["hysteria", "hysteria2"] or not ranges:
            return flag
    except Exception:
        return False

    return parse_port_ranges(ranges)


def parse_port_ranges(ranges) -> bool:
    text = wrap(ranges)
    if not text:
        return False

    nums = re.split(r"/|,", text)
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
        except Exception:
            return False

    return True


def check_required_port(item: dict, protocol: str) -> bool:
    return check_ports(item.get("port", ""), item.get("ports", None), protocol)


def check_optional_port(item: dict, protocol: str) -> bool:
    if "port" not in item or item.get("port") in (None, ""):
        return True
    return check_ports(item.get("port", ""), item.get("ports", None), protocol)


def check_common_optional(item: dict) -> bool:
    if "uuid" in item and not utils.verify_uuid(item.get("uuid")):
        return False

    for attribute in ["servername", "sni"]:
        if attribute in item and type(item[attribute]) != str:
            return False

    for attribute in BOOL_FIELDS:
        if attribute in item and type(item[attribute]) != bool:
            return False

    if "ip-version" in item:
        version = utils.trim(str(item.get("ip-version", "")))
        if version and version not in IP_VERSIONS:
            return False

    if "alpn" in item and type(item["alpn"]) != list:
        return False

    return True


def finalize_auth(item: dict, field: str | None) -> bool:
    if not field:
        return True
    if not item.get(field, ""):
        return False
    if utils.is_number(item[field]):
        item[field] = QuotedStr(item[field])
    return True


def quote_numeric_fields(item: dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        if field in item and item.get(field, "") != "" and utils.is_number(item[field]):
            item[field] = QuotedStr(item[field])


def ensure_non_negative_number(item: dict, field: str) -> bool:
    if field not in item:
        return True
    if not utils.is_number(item[field]) or int(item[field]) < 0:
        return False
    return True


def ensure_number(item: dict, field: str) -> bool:
    if field not in item:
        return True
    return utils.is_number(item[field])


def ensure_bool(item: dict, field: str) -> bool:
    if field not in item:
        return True
    return type(item[field]) == bool


def ensure_str(item: dict, field: str) -> bool:
    if field not in item:
        return True
    return type(item[field]) == str


def is_valid_ip(text: str) -> bool:
    text = utils.trim(text)
    if not text:
        return False
    try:
        ipaddress.ip_address(text)
        return True
    except Exception:
        return False


def verify_traffic(item: dict, field: str) -> bool:
    if field not in item:
        return True

    traffic = item.get(field, "")
    if traffic == "null":
        item.pop(field)
        return True

    if traffic and utils.is_number(traffic):
        traffic = str(traffic)
        item[field] = traffic

    return bool(TRAFFIC_PATTERN.match(utils.trim(traffic)))


def verify_congestion_controller(item: dict) -> bool:
    if "congestion-controller" not in item:
        return True
    return item.get("congestion-controller") in CONGESTION_CONTROLLERS


def verify_bbr_profile(item: dict) -> bool:
    if "bbr-profile" not in item:
        return True
    profile = wrap(item.get("bbr-profile", ""))
    return profile in BBR_PROFILES


def verify_hop_interval(item: dict) -> bool:
    if "hop-interval" not in item:
        return True
    value = item.get("hop-interval")
    if utils.is_number(value):
        return float(value) >= 0

    text = wrap(value)
    if not text or "," in text:
        return False
    if "-" not in text:
        return False
    start, end = text.split("-", maxsplit=1)
    try:
        start, end = float(start), float(end)
        return start > 0 and end >= start
    except Exception:
        return False


def endpoint_key(item: dict) -> str:
    server = item.get("server")
    port = item.get("port")
    if server:
        return f"{server}:{port}"
    return f"{item.get('type')}:{item.get('name')}"
