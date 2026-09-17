# -*- coding: utf-8 -*-

from __future__ import annotations

import utils
from outbound.base import OutboundVerifier, VerifyContext
from outbound.common import QuotedStr


class _UserPassVerifier(OutboundVerifier):
    def verify_fields(self, item: dict[str, object], ctx: VerifyContext) -> bool:
        for field in ("username", "password"):
            value = item.get(field, None)
            if not value:
                continue
            if not isinstance(value, str) and not utils.is_number(value):
                return False
            if utils.is_number(value):
                item[field] = QuotedStr(value)
            else:
                item[field] = utils.trim(value)
        return True

    def auth_field(self, item: dict[str, object]) -> str | None:
        return None

    def duplicate_key(self, item: dict[str, object]) -> tuple[str, object]:
        return (self.type_name,)


class HttpVerifier(_UserPassVerifier):
    type_name = "http"


class Socks5Verifier(_UserPassVerifier):
    type_name = "socks5"
