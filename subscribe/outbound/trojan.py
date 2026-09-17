# -*- coding: utf-8 -*-

from __future__ import annotations

from outbound.base import OutboundVerifier, VerifyContext
from outbound.common import wrap
from outbound.tls import verify_reality_opts
from outbound.transport import verify_grpc_opts, verify_ws_opts


class TrojanVerifier(OutboundVerifier):
    type_name = "trojan"

    def verify_fields(self, item: dict[str, object], ctx: VerifyContext) -> bool:
        network = wrap(item.get("network", ""))
        if network and network not in ("tcp", "ws", "grpc"):
            return False

        # Trojan outbound no longer has flow; drop leftover XTLS values
        item.pop("flow", None)

        if not verify_ws_opts(item, network):
            return False
        if not verify_grpc_opts(item, network):
            return False
        if ctx.is_mihomo and not verify_reality_opts(item):
            return False

        if "ss-opts" in item:
            ss_opts = item.get("ss-opts")
            if type(ss_opts) != dict:
                return False
        return True
