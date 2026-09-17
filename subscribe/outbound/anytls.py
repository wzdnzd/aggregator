# -*- coding: utf-8 -*-

from __future__ import annotations

from outbound.base import OutboundVerifier, VerifyContext
from outbound.common import ensure_non_negative_number
from outbound.tls import verify_optional_str_dict


class AnyTLSVerifier(OutboundVerifier):
    type_name = "anytls"
    mihomo_only = True

    def verify_fields(self, item: dict[str, object], ctx: VerifyContext) -> bool:
        for field in ("idle-session-check-interval", "idle-session-timeout", "min-idle-session"):
            if not ensure_non_negative_number(item, field):
                return False
        if not verify_optional_str_dict(item, "shadow-tls-opts"):
            return False
        if not verify_optional_str_dict(item, "restls-opts"):
            return False
        if not verify_optional_str_dict(item, "jls-opts"):
            return False
        return True
