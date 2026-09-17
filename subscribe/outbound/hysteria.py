# -*- coding: utf-8 -*-

from __future__ import annotations

from outbound.base import OutboundVerifier, VerifyContext
from outbound.common import (
    ensure_bool,
    ensure_number,
    ensure_str,
    parse_port_ranges,
    verify_bbr_profile,
    verify_hop_interval,
    verify_traffic,
    wrap,
)

HYSTERIA_PROTOCOLS = ("udp", "wechat-video", "faketcp")
HYSTERIA2_OBFS = ("salamander", "gecko")


class HysteriaVerifier(OutboundVerifier):
    type_name = "hysteria"
    mihomo_only = True

    def verify_fields(self, item: dict[str, object], ctx: VerifyContext) -> bool:
        if not verify_traffic(item, "up") or not verify_traffic(item, "down"):
            return False
        for field in ("ca", "ca-str", "auth-str", "auth_str", "obfs"):
            if not ensure_str(item, field):
                return False
        for field in ("disable_mtu_discovery", "fast-open"):
            if not ensure_bool(item, field):
                return False
        if "protocol" in item and wrap(item.get("protocol", "")) not in HYSTERIA_PROTOCOLS:
            return False
        if "ports" in item and not parse_port_ranges(item.get("ports")):
            return False
        for field in ("recv_window_conn", "recv-window-conn", "recv_window", "recv-window"):
            if not ensure_number(item, field):
                return False
        return True

    def auth_field(self, item: dict[str, object]) -> str | None:
        return "auth-str" if "auth-str" in item else "auth_str"

    def duplicate_key(self, item: dict[str, object]) -> tuple[str, object]:
        field = self.auth_field(item)
        return (self.type_name, item.get(field, ""))


class Hysteria2Verifier(OutboundVerifier):
    type_name = "hysteria2"
    mihomo_only = True

    def verify_fields(self, item: dict[str, object], ctx: VerifyContext) -> bool:
        if not verify_traffic(item, "up") or not verify_traffic(item, "down"):
            return False
        for field in ("ca", "ca-str", "obfs-password"):
            if not ensure_str(item, field):
                return False
        if "ports" in item and not parse_port_ranges(item.get("ports")):
            return False
        if not verify_hop_interval(item) or not verify_bbr_profile(item):
            return False

        obfs = wrap(item.get("obfs", ""))
        if obfs:
            if obfs not in HYSTERIA2_OBFS:
                return False
            if not wrap(item.get("obfs-password", "")):
                return False
        return True
