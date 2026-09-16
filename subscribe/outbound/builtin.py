# -*- coding: utf-8 -*-

from __future__ import annotations

from outbound.base import OutboundVerifier, VerifyContext
from outbound.common import ensure_str


class _BuiltinVerifier(OutboundVerifier):
    mihomo_only = True
    require_server = False
    require_port = False

    def verify_fields(self, item: dict, ctx: VerifyContext) -> bool:
        return True

    def auth_field(self, item: dict) -> str | None:
        return None

    def duplicate_key(self, item: dict) -> tuple:
        return (self.type_name, item.get("name", ""))


class DirectVerifier(_BuiltinVerifier):
    type_name = "direct"


class DnsVerifier(_BuiltinVerifier):
    type_name = "dns"


class RejectVerifier(_BuiltinVerifier):
    type_name = "reject"


class RematchVerifier(_BuiltinVerifier):
    type_name = "rematch"

    def verify_fields(self, item: dict, ctx: VerifyContext) -> bool:
        return ensure_str(item, "target-rematch-name") and ensure_str(item, "target-sub-rule")
