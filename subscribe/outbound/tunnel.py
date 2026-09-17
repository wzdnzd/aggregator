# -*- coding: utf-8 -*-

from __future__ import annotations

from outbound.base import OutboundVerifier, VerifyContext
from outbound.common import (
    quote_numeric_fields,
    verify_bbr_profile,
    verify_congestion_controller,
    wrap,
)


class TrustTunnelVerifier(OutboundVerifier):
    type_name = "trusttunnel"
    mihomo_only = True

    def verify_fields(self, item: dict[str, object], ctx: VerifyContext) -> bool:
        if not wrap(item.get("username", "")):
            return False
        quote_numeric_fields(item, ("username",))
        if not verify_congestion_controller(item) or not verify_bbr_profile(item):
            return False
        return True

    def duplicate_key(self, item: dict[str, object]) -> tuple[str, object]:
        return (self.type_name, item.get("username", ""), item.get("password", ""))


class GostRelayVerifier(OutboundVerifier):
    type_name = "gost-relay"
    mihomo_only = True

    def verify_fields(self, item: dict[str, object], ctx: VerifyContext) -> bool:
        quote_numeric_fields(item, ("username", "password"))
        return True

    def auth_field(self, item: dict[str, object]) -> str | None:
        return None

    def duplicate_key(self, item: dict[str, object]) -> tuple[str, object]:
        return (self.type_name, item.get("username", ""), item.get("password", ""))
