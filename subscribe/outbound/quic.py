# -*- coding: utf-8 -*-

from __future__ import annotations

from outbound.base import OutboundVerifier, VerifyContext
from outbound.common import (
    ensure_bool,
    ensure_number,
    is_valid_ip,
    quote_numeric_fields,
    verify_bbr_profile,
    verify_congestion_controller,
    verify_traffic,
    wrap,
)

TUIC_UDP_RELAY_MODES = ("native", "quic")
SHADOWQUIC_VERSIONS = ("v1", "v2")


class TuicVerifier(OutboundVerifier):
    type_name = "tuic"
    mihomo_only = True

    def verify_fields(self, item: dict, ctx: VerifyContext) -> bool:
        token = wrap(item.get("token", ""))
        uuid = wrap(item.get("uuid", ""))
        password = wrap(item.get("password", ""))

        if token:
            if uuid or password:
                return False
            item["token"] = token
        elif uuid:
            if not password:
                return False
            item["password"] = password
        else:
            return False

        for field in ("disable-sni", "reduce-rtt", "fast-open"):
            if not ensure_bool(item, field):
                return False
        for field in ("heartbeat-interval", "request-timeout", "max-udp-relay-packet-size", "max-open-streams"):
            if not ensure_number(item, field):
                return False
        if "udp-relay-mode" in item and item["udp-relay-mode"] not in TUIC_UDP_RELAY_MODES:
            return False
        if not verify_congestion_controller(item) or not verify_bbr_profile(item):
            return False
        if "ip" in item and not is_valid_ip(item.get("ip", "")):
            return False
        return True

    def auth_field(self, item: dict) -> str | None:
        return "token" if wrap(item.get("token", "")) else "uuid"

    def duplicate_key(self, item: dict) -> tuple:
        if wrap(item.get("token", "")):
            return (self.type_name, item.get("token", ""))
        return (self.type_name, item.get("uuid", ""))


class ShadowQuicVerifier(OutboundVerifier):
    type_name = "shadowquic"
    mihomo_only = True

    def verify_fields(self, item: dict, ctx: VerifyContext) -> bool:
        if not wrap(item.get("username", "")):
            return False
        quote_numeric_fields(item, ("username",))
        if not verify_congestion_controller(item) or not verify_bbr_profile(item):
            return False
        if not verify_traffic(item, "up") or not verify_traffic(item, "down"):
            return False
        if "quic-versions" in item:
            versions = item.get("quic-versions")
            if type(versions) != list:
                return False
            for version in versions:
                if wrap(version) not in SHADOWQUIC_VERSIONS:
                    return False
        return True

    def duplicate_key(self, item: dict) -> tuple:
        return (self.type_name, item.get("username", ""), item.get("password", ""))
