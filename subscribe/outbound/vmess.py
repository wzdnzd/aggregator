# -*- coding: utf-8 -*-

from __future__ import annotations

import utils
from outbound.base import OutboundVerifier, VerifyContext
from outbound.tls import verify_reality_opts
from outbound.transport import (
    normalize_httpupgrade,
    verify_grpc_opts,
    verify_h2_opts,
    verify_http_opts,
    verify_mekya_opts,
    verify_mkcp_opts,
    verify_ws_opts,
)

VMESS_CIPHERS = ["auto", "aes-128-gcm", "chacha20-poly1305", "none"]
VMESS_NETWORKS = ("tcp", "ws", "h2", "http", "grpc", "mkcp", "kcp", "mekya")


class VmessVerifier(OutboundVerifier):
    type_name = "vmess"

    def verify_fields(self, item: dict[str, object], ctx: VerifyContext) -> bool:
        network = normalize_httpupgrade(item)
        if not network:
            for key, value in (
                ("ws-opts", "ws"),
                ("http-opts", "http"),
                ("h2-opts", "h2"),
                ("grpc-opts", "grpc"),
                ("mkcp-opts", "mkcp"),
                ("mekya-opts", "mekya"),
            ):
                if key in item:
                    network = value
                    break
            else:
                network = "tcp" if ctx.is_mihomo else "ws"

        allowed = VMESS_NETWORKS if ctx.is_mihomo else ("ws", "h2", "http", "grpc")
        if network not in allowed:
            return False

        ciphers = VMESS_CIPHERS + ["zero"] if ctx.is_mihomo else VMESS_CIPHERS
        if item.get("cipher") not in ciphers:
            return False
        if "alterId" not in item or not utils.is_number(item["alterId"]):
            return False

        if not verify_h2_opts(item, network):
            return False
        if not verify_http_opts(item, network):
            return False
        if not verify_ws_opts(item, network):
            return False
        if "grpc-opts" in item:
            if not ctx.is_mihomo:
                return False
            if not verify_grpc_opts(item, network):
                return False
        if ctx.is_mihomo:
            if not verify_mkcp_opts(item, network):
                return False
            if not verify_mekya_opts(item, network):
                return False
            if not verify_reality_opts(item):
                return False
        return True

    def auth_field(self, item: dict[str, object]) -> str | None:
        return "uuid"
