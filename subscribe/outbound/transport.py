# -*- coding: utf-8 -*-

from __future__ import annotations

import utils

from outbound.common import wrap

# mihomo ParseRange uses strconv.Atoi
XHTTP_RANGE_MAX = 2**63 - 1
XHTTP_RANGE_FIELDS = (
    "sc-max-each-post-bytes",
    "sc-min-posts-interval-ms",
    "x-padding-bytes",
    "uplink-chunk-size",
    "session-length",
)
XHTTP_RANGE_POSITIVE_MAX = set(["sc-max-each-post-bytes", "sc-min-posts-interval-ms"])
XHTTP_REUSE_RANGE_FIELDS = (
    "max-concurrency",
    "max-connections",
    "c-max-reuse-times",
    "h-max-request-times",
    "h-max-reusable-secs",
)
XHTTP_MODES = ("auto", "stream-one", "stream-up", "packet-up")
MKCP_HEADERS = ("", "none", "srtp", "utp", "wechat-video", "dtls", "wireguard")


def parse_xhttp_range_bound(text: str):
    text = utils.trim(text)
    if not text:
        return None

    if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
        try:
            value = int(text)
        except Exception:
            return None
    else:
        try:
            number = float(text)
        except Exception:
            return None
        if number != number or number == float("inf") or number == float("-inf"):
            return None
        value = int(number)
        if value != number:
            return None

    if abs(value) > XHTTP_RANGE_MAX:
        return None
    return value


def normalize_xhttp_range(value, allow_negative: bool = False):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        if (value < 0 and not allow_negative) or abs(value) > XHTTP_RANGE_MAX:
            return None
        return str(value)
    if isinstance(value, float):
        if value != value or value == float("inf") or value == float("-inf"):
            return None
        if value < 0 and not allow_negative:
            return None
        number = int(value)
        if number != value or abs(number) > XHTTP_RANGE_MAX:
            return None
        return str(number)

    text = utils.trim(str(value))
    if not text:
        return ""

    bound = parse_xhttp_range_bound(text)
    if bound is not None:
        if bound < 0 and not allow_negative:
            return None
        return str(bound)

    if text.count("-") != 1:
        return None
    left, right = text.split("-", 1)
    min_val, max_val = parse_xhttp_range_bound(left), parse_xhttp_range_bound(right)
    if min_val is None or max_val is None or max_val < min_val:
        return None
    if min_val < 0 and not allow_negative:
        return None
    if min_val == max_val:
        return str(min_val)
    return f"{min_val}-{max_val}"


def apply_xhttp_range_field(container: dict, key: str, min_positive: bool = False, max_positive: bool = False) -> bool:
    if key not in container:
        return True

    value = container[key]
    if value is None or (isinstance(value, str) and not utils.trim(value)):
        container.pop(key, None)
        return True

    normalized = normalize_xhttp_range(value)
    if normalized is None:
        return False
    if not normalized:
        container.pop(key, None)
        return True

    parts = normalized.split("-")
    min_val, max_val = int(parts[0]), int(parts[-1])
    if min_positive and min_val <= 0:
        return False
    if max_positive and max_val <= 0:
        return False

    container[key] = min_val if len(parts) == 1 else normalized
    return True


def verify_xhttp_reuse_settings(settings: dict) -> bool:
    if type(settings) != dict:
        return False

    for key in XHTTP_REUSE_RANGE_FIELDS:
        if not apply_xhttp_range_field(settings, key):
            return False

    if "h-keep-alive-period" not in settings:
        return True

    value = settings["h-keep-alive-period"]
    if value is None or (isinstance(value, str) and not utils.trim(value)):
        settings.pop("h-keep-alive-period", None)
        return True

    # wiki allows negatives such as -1 to disable keepalive
    normalized = normalize_xhttp_range(value, allow_negative=True)
    if not normalized or "-" in normalized[1:]:
        return False

    settings["h-keep-alive-period"] = int(normalized)
    return True


def verify_ws_opts(item: dict, network: str) -> bool:
    if "ws-opts" not in item:
        return True
    if network != "ws":
        return False

    ws_opts = item.get("ws-opts", {})
    if not ws_opts or type(ws_opts) != dict:
        return False
    if "path" in ws_opts and type(ws_opts["path"]) != str:
        return False
    if "headers" in ws_opts and type(ws_opts["headers"]) != dict:
        return False
    return True


def verify_grpc_opts(item: dict, network: str) -> bool:
    if "grpc-opts" not in item:
        return True
    if network != "grpc":
        return False

    grpc_opts = item.get("grpc-opts", {})
    if not grpc_opts or type(grpc_opts) != dict:
        return False
    if "grpc-service-name" in grpc_opts and type(grpc_opts["grpc-service-name"]) != str:
        return False
    return True


def verify_http_opts(item: dict, network: str) -> bool:
    if "http-opts" not in item:
        return True
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
    return True


def verify_h2_opts(item: dict, network: str) -> bool:
    if "h2-opts" not in item:
        return True
    if network != "h2":
        return False

    h2_opts = item.get("h2-opts", {})
    if not h2_opts or type(h2_opts) != dict:
        return False
    if "host" in h2_opts and type(h2_opts["host"]) != list:
        return False
    return True


def verify_mkcp_opts(item: dict, network: str) -> bool:
    if "mkcp-opts" not in item:
        return True
    if network not in ("mkcp", "kcp"):
        return False

    mkcp_opts = item.get("mkcp-opts", {})
    if type(mkcp_opts) != dict:
        return False
    if "header" in mkcp_opts:
        header = wrap(mkcp_opts.get("header", ""))
        if header not in MKCP_HEADERS:
            return False
    return True


def verify_mekya_opts(item: dict, network: str) -> bool:
    if "mekya-opts" not in item:
        return True
    if network != "mekya":
        return False

    mekya_opts = item.get("mekya-opts", {})
    if not mekya_opts or type(mekya_opts) != dict:
        return False
    if "url" in mekya_opts and type(mekya_opts["url"]) != str:
        return False
    if "kcp" in mekya_opts and type(mekya_opts["kcp"]) != dict:
        return False
    return True


def verify_xhttp_opts(item: dict, network: str) -> bool:
    if "xhttp-opts" not in item:
        return True
    if network != "xhttp":
        return False

    xhttp_opts = item.get("xhttp-opts", {})
    if not xhttp_opts or type(xhttp_opts) != dict:
        return False
    if "path" in xhttp_opts and type(xhttp_opts["path"]) != str:
        return False
    if "host" in xhttp_opts and type(xhttp_opts["host"]) != str:
        return False

    if "mode" in xhttp_opts:
        xhttp_mode = wrap(xhttp_opts.get("mode", ""))
        if xhttp_mode and xhttp_mode not in XHTTP_MODES:
            return False
    if "headers" in xhttp_opts and type(xhttp_opts["headers"]) != dict:
        return False

    for key in XHTTP_RANGE_FIELDS:
        min_positive = key == "session-length"
        max_positive = key in XHTTP_RANGE_POSITIVE_MAX
        if not apply_xhttp_range_field(xhttp_opts, key, min_positive=min_positive, max_positive=max_positive):
            return False

    if "reuse-settings" in xhttp_opts and not verify_xhttp_reuse_settings(xhttp_opts.get("reuse-settings")):
        return False
    if "download-settings" in xhttp_opts:
        download_settings = xhttp_opts.get("download-settings")
        if type(download_settings) != dict:
            return False
        if "reuse-settings" in download_settings and not verify_xhttp_reuse_settings(
            download_settings.get("reuse-settings")
        ):
            return False
    return True


def normalize_httpupgrade(item: dict) -> str:
    network = wrap(item.get("network", ""))
    if network != "httpupgrade":
        return network

    item["network"] = "ws"
    ws_opts = item.get("ws-opts")
    if ws_opts is None or ws_opts == "":
        ws_opts = {}
        item["ws-opts"] = ws_opts
    if type(ws_opts) != dict:
        return "ws"
    ws_opts["v2ray-http-upgrade"] = True
    return "ws"
