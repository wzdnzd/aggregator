# -*- coding: utf-8 -*-

from __future__ import annotations

from outbound.base import OutboundVerifier, VerifyContext
from outbound.common import wrap


class EasyTierVerifier(OutboundVerifier):
    type_name = "easytier"
    mihomo_only = True
    require_server = False
    require_port = False

    def verify_fields(self, item: dict, ctx: VerifyContext) -> bool:
        if not wrap(item.get("network-name", "")):
            return False
        peers = item.get("peers")
        listeners = item.get("listeners")
        has_peers = isinstance(peers, list) and any(wrap(p) if not isinstance(p, dict) else True for p in peers)
        has_listeners = isinstance(listeners, list) and listeners
        return bool(has_peers or has_listeners)

    def auth_field(self, item: dict) -> str | None:
        return None

    def duplicate_key(self, item: dict) -> tuple:
        return (self.type_name, item.get("network-name", ""), item.get("network-secret", ""))


class TailscaleVerifier(OutboundVerifier):
    type_name = "tailscale"
    mihomo_only = True
    require_server = False
    require_port = False

    def verify_fields(self, item: dict, ctx: VerifyContext) -> bool:
        return True

    def auth_field(self, item: dict) -> str | None:
        return None

    def duplicate_key(self, item: dict) -> tuple:
        return (self.type_name, item.get("auth-key", ""), item.get("hostname", ""), item.get("control-url", ""))


class ZeroTierVerifier(OutboundVerifier):
    type_name = "zerotier"
    mihomo_only = True
    require_server = False
    require_port = False

    def verify_fields(self, item: dict, ctx: VerifyContext) -> bool:
        network = wrap(item.get("network", ""))
        return len(network) == 16

    def auth_field(self, item: dict) -> str | None:
        return None

    def duplicate_key(self, item: dict) -> tuple:
        return (self.type_name, item.get("network", ""), item.get("identity-secret", ""))
