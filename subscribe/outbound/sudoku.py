# -*- coding: utf-8 -*-

from __future__ import annotations

import utils
from outbound.base import OutboundVerifier, VerifyContext
from outbound.common import ensure_bool, quote_numeric_fields, wrap

SUDOKU_AEAD = ("", "chacha20-poly1305", "aes-128-gcm", "none")
SUDOKU_TABLES = ("", "prefer_ascii", "prefer_entropy", "up_ascii_down_entropy", "up_entropy_down_ascii")
SUDOKU_MULTIPLEX = ("", "off", "auto", "on")
HTTPMASK_MODES = ("", "legacy", "stream", "poll", "auto", "ws")


class SudokuVerifier(OutboundVerifier):
    type_name = "sudoku"
    mihomo_only = True

    def verify_fields(self, item: dict[str, object], ctx: VerifyContext) -> bool:
        if not wrap(item.get("key", "")):
            return False
        quote_numeric_fields(item, ("key",))
        if "aead-method" in item and wrap(item.get("aead-method", "")) not in SUDOKU_AEAD:
            return False
        if "table-type" in item and wrap(item.get("table-type", "")) not in SUDOKU_TABLES:
            return False
        if "multiplex" in item and wrap(item.get("multiplex", "")) not in SUDOKU_MULTIPLEX:
            return False
        for field in ("padding-min", "padding-max"):
            if field in item:
                if not utils.is_number(item[field]):
                    return False
                value = int(item[field])
                if value < 0 or value > 100:
                    return False
        if "padding-min" in item and "padding-max" in item and int(item["padding-min"]) > int(item["padding-max"]):
            return False
        if not ensure_bool(item, "enable-pure-downlink"):
            return False
        if "httpmask" in item:
            httpmask = item.get("httpmask")
            if type(httpmask) != dict:
                return False
            if "mode" in httpmask and wrap(httpmask.get("mode", "")) not in HTTPMASK_MODES:
                return False
        return True

    def auth_field(self, item: dict[str, object]) -> str | None:
        return "key"
