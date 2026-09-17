# -*- coding: utf-8 -*-

from __future__ import annotations

import base64
import re

import utils
from outbound.common import QuotedStr, wrap


def verify_reality_public_key(public_key: str) -> bool:
    # mihomo uses base64.RawURLEncoding and requires 32 bytes
    public_key = utils.trim(public_key)
    if not public_key or not re.fullmatch(r"[A-Za-z0-9_-]+", public_key):
        return False

    try:
        decoded = base64.urlsafe_b64decode(public_key + "=" * (-len(public_key) % 4))
    except Exception:
        return False

    if len(decoded) != 32:
        return False

    canonical = base64.urlsafe_b64encode(decoded).decode("utf-8").rstrip("=")
    return canonical == public_key


def verify_reality_opts(item: dict[str, object], required: bool = False) -> bool:
    if "reality-opts" not in item:
        return not required

    reality_opts = item.get("reality-opts", {})
    if not reality_opts or type(reality_opts) != dict:
        return False
    if "public-key" not in reality_opts or type(reality_opts["public-key"]) != str:
        return False

    content = utils.trim(reality_opts["public-key"])
    if not verify_reality_public_key(content):
        return False
    reality_opts["public-key"] = content

    if "short-id" not in reality_opts:
        return True

    short_id = reality_opts["short-id"]
    if type(short_id) != str:
        if utils.is_number(short_id):
            short_id = str(short_id)
        else:
            return False

    if short_id:
        try:
            sib = bytes.fromhex(short_id)
            if len(sib) > 8:
                return False
        except ValueError:
            return False

    reality_opts["short-id"] = QuotedStr(short_id)
    return True


def verify_optional_str_dict(item: dict[str, object], field: str, required_keys: tuple[str, ...] = ()) -> bool:
    if field not in item:
        return True
    opts = item.get(field)
    if type(opts) != dict:
        return False
    for key in required_keys:
        if key not in opts:
            return False
        if type(opts.get(key)) != str or not wrap(opts.get(key)):
            return False
    return True
