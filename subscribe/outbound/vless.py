# -*- coding: utf-8 -*-

from __future__ import annotations

import base64
import re

from outbound.base import OutboundVerifier, VerifyContext
from outbound.common import wrap
from outbound.tls import verify_reality_opts
from outbound.transport import (
    verify_grpc_opts,
    verify_h2_opts,
    verify_http_opts,
    verify_ws_opts,
    verify_xhttp_opts,
)

VLESS_MLKEM_X25519_PLUS_PREFIX = "mlkem768x25519plus"
VLESS_MLKEM_X25519_PLUS_MODES = ("native", "xorpub", "random")
VLESS_MLKEM_X25519_PLUS_RTTS = ("1rtt", "0rtt")
VLESS_MLKEM_X25519_PLUS_PADDING_LIMIT = 20
VLESS_MLKEM_X25519_PLUS_KEY_SIZES = (32, 1184)
VLESS_VISION_FLOW = "xtls-rprx-vision"


def verify_vless_encryption(encryption: str) -> bool:
    if not encryption or encryption == "none":
        return True

    parts = encryption.split(".")
    if (
        len(parts) < 4
        or parts[0] != VLESS_MLKEM_X25519_PLUS_PREFIX
        or parts[1] not in VLESS_MLKEM_X25519_PLUS_MODES
        or parts[2] not in VLESS_MLKEM_X25519_PLUS_RTTS
    ):
        return False

    for key in parts[3:]:
        if len(key) < VLESS_MLKEM_X25519_PLUS_PADDING_LIMIT:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            return False

        try:
            content = key + "=" * (-len(key) % 4)
            decoded = base64.urlsafe_b64decode(content)
        except Exception:
            return False

        if len(decoded) not in VLESS_MLKEM_X25519_PLUS_KEY_SIZES:
            return False

    return True


class VlessVerifier(OutboundVerifier):
    type_name = "vless"
    mihomo_only = True

    def verify_fields(self, item: dict[str, object], ctx: VerifyContext) -> bool:
        encryption = wrap(item.get("encryption", ""))
        if not verify_vless_encryption(encryption):
            return False

        network = wrap(item.get("network", "tcp")) or "tcp"
        if network not in ("ws", "tcp", "grpc", "http", "h2", "xhttp"):
            return False

        if "flow" in item:
            flow = wrap(item.get("flow", ""))
            if flow:
                # mihomo truncates flow to 16 chars, so vision-udp443 is valid
                if flow[:16] != VLESS_VISION_FLOW:
                    return False
                item["flow"] = VLESS_VISION_FLOW

        if not verify_ws_opts(item, network):
            return False
        if not verify_grpc_opts(item, network):
            return False
        if not verify_http_opts(item, network):
            return False
        if not verify_h2_opts(item, network):
            return False
        if not verify_reality_opts(item):
            return False
        if not verify_xhttp_opts(item, network):
            return False
        return True

    def auth_field(self, item: dict[str, object]) -> str | None:
        return "uuid"
