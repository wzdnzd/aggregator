# -*- coding: utf-8 -*-

from __future__ import annotations

from outbound.base import OutboundVerifier, VerifyContext
from outbound.common import quote_numeric_fields, wrap


class SshVerifier(OutboundVerifier):
    type_name = "ssh"
    mihomo_only = True

    def verify_fields(self, item: dict, ctx: VerifyContext) -> bool:
        if not wrap(item.get("username", "")):
            return False
        quote_numeric_fields(item, ("username",))
        has_password = bool(wrap(item.get("password", "")))
        has_key = bool(wrap(item.get("private-key", "")) or wrap(item.get("private_key", "")))
        return has_password or has_key

    def auth_field(self, item: dict) -> str | None:
        if wrap(item.get("password", "")):
            return "password"
        return None

    def duplicate_key(self, item: dict) -> tuple:
        return (
            self.type_name,
            item.get("username", ""),
            item.get("password", ""),
            item.get("private-key", "") or item.get("private_key", ""),
        )
