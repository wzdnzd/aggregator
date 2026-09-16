# -*- coding: utf-8 -*-

from __future__ import annotations

from outbound.base import OutboundVerifier, VerifyContext
from outbound.common import parse_port_ranges, quote_numeric_fields, wrap

MIERU_TRANSPORTS = ("TCP", "UDP")
MIERU_MULTIPLEXING = (
    "",
    "MULTIPLEXING_OFF",
    "MULTIPLEXING_LOW",
    "MULTIPLEXING_MIDDLE",
    "MULTIPLEXING_HIGH",
)
MIERU_HANDSHAKE = ("", "HANDSHAKE_STANDARD", "HANDSHAKE_NO_WAIT")


class MieruVerifier(OutboundVerifier):
    type_name = "mieru"
    mihomo_only = True
    require_port = False

    def verify_fields(self, item: dict, ctx: VerifyContext) -> bool:
        has_port = "port" in item and item.get("port") not in (None, "")
        has_range = bool(wrap(item.get("port-range", "")))
        if has_port == has_range:
            return False
        if has_range and not parse_port_ranges(item.get("port-range")):
            return False
        if not wrap(item.get("username", "")):
            return False
        quote_numeric_fields(item, ("username",))

        transport = wrap(item.get("transport", "TCP")).upper() or "TCP"
        if transport not in MIERU_TRANSPORTS:
            return False
        if "multiplexing" in item and wrap(item.get("multiplexing", "")) not in MIERU_MULTIPLEXING:
            return False
        if "handshake-mode" in item and wrap(item.get("handshake-mode", "")) not in MIERU_HANDSHAKE:
            return False
        return True

    def duplicate_key(self, item: dict) -> tuple:
        return (self.type_name, item.get("username", ""), item.get("password", ""))
