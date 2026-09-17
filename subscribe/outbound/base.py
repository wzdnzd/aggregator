# -*- coding: utf-8 -*-

from __future__ import annotations

from abc import ABC, abstractmethod

import utils
from outbound.common import (
    check_common_optional,
    check_optional_port,
    check_required_port,
    endpoint_key,
    finalize_auth,
    normalize_name,
    normalize_server,
)


class VerifyContext:
    def __init__(self, is_mihomo: bool = True) -> None:
        self.is_mihomo = is_mihomo


class OutboundVerifier(ABC):
    type_name: str = ""
    mihomo_only: bool = False
    require_server: bool = True
    require_port: bool = True

    def verify(self, item: dict[str, object], ctx: VerifyContext) -> bool:
        if self.mihomo_only and not ctx.is_mihomo:
            return False

        item.pop("dialer-proxy", None)

        if not normalize_name(item):
            return False

        if (self.needs_server(item) or item.get("server")) and not normalize_server(item):
            return False

        if self.needs_port(item):
            if not check_required_port(item, item.get("type", self.type_name)):
                return False
        elif not check_optional_port(item, item.get("type", self.type_name)):
            return False

        if not check_common_optional(item):
            return False
        if not self.verify_fields(item, ctx):
            return False
        return finalize_auth(item, self.auth_field(item))

    def needs_server(self, item: dict[str, object]) -> bool:
        return self.require_server

    def needs_port(self, item: dict[str, object]) -> bool:
        return self.require_port

    @abstractmethod
    def verify_fields(self, item: dict[str, object], ctx: VerifyContext) -> bool:
        raise NotImplementedError

    def auth_field(self, item: dict[str, object]) -> str | None:
        return "password"

    def duplicate_key(self, item: dict[str, object]) -> tuple[str, object]:
        field = self.auth_field(item)
        secret = item.get(field, "") if field else ""
        return (self.type_name, secret)


VERIFIERS: dict[str, OutboundVerifier] = {}


def get_verifier(type_name: str) -> OutboundVerifier | None:
    return VERIFIERS.get(utils.trim(str(type_name or "")).lower())


def register(*verifiers: OutboundVerifier) -> None:
    for verifier in verifiers:
        VERIFIERS[verifier.type_name] = verifier


def verify(item: dict[str, object], is_mihomo: bool = True) -> bool:
    if not item or type(item) != dict or "type" not in item:
        return False

    verifier = get_verifier(str(item.get("type", "")))
    if verifier is None:
        return False

    try:
        return verifier.verify(item, VerifyContext(is_mihomo=is_mihomo))
    except Exception:
        return False


def proxy_exists(proxy: dict[str, object], hosts: dict[str, list[dict[str, object]]]) -> bool:
    if not proxy:
        return True
    if not hosts:
        return False

    existing = hosts.get(endpoint_key(proxy), [])
    if not existing:
        return False

    protocol = utils.trim(str(proxy.get("type", ""))).lower()
    if protocol in ("http", "socks5"):
        return True

    verifier = get_verifier(protocol)
    if verifier is None:
        return False

    current = verifier.duplicate_key(proxy)
    return any(p.get("type") == protocol and verifier.duplicate_key(p) == current for p in existing)
