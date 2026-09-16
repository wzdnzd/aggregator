# -*- coding: utf-8 -*-

from __future__ import annotations

from outbound.base import OutboundVerifier, VerifyContext
from outbound.common import wrap

OPENVPN_PROTOS = ("", "udp", "tcp")
OPENVPN_CIPHERS = (
    "",
    "AES-128-GCM",
    "AES-192-GCM",
    "AES-256-GCM",
    "AES-128-CBC",
    "AES-192-CBC",
    "AES-256-CBC",
    "AES-CBC",
    "CHACHA20-POLY1305",
)
OPENVPN_AUTH = ("", "MD5", "SHA1", "SHA256", "SHA384", "SHA512")
OPENVPN_COMP = ("", "yes", "no", "adaptive")
OPENVPN_CIPHERS_UPPER = {c.upper() for c in OPENVPN_CIPHERS}
MASQUE_NETWORKS = ("", "quic", "h2", "h3-l4proxy")


class WireGuardVerifier(OutboundVerifier):
    type_name = "wireguard"
    mihomo_only = True

    def needs_server(self, item: dict) -> bool:
        peers = item.get("peers")
        return not (isinstance(peers, list) and peers)

    def needs_port(self, item: dict) -> bool:
        return self.needs_server(item)

    def verify_fields(self, item: dict, ctx: VerifyContext) -> bool:
        if not wrap(item.get("private-key", "")):
            return False
        peers = item.get("peers")
        if isinstance(peers, list) and peers:
            for peer in peers:
                if type(peer) != dict:
                    return False
                if not wrap(peer.get("public-key", "")):
                    return False
                if "allowed-ips" not in peer:
                    return False
            return True
        return bool(wrap(item.get("public-key", "")))

    def auth_field(self, item: dict) -> str | None:
        return None

    def duplicate_key(self, item: dict) -> tuple:
        return (self.type_name, item.get("private-key", ""), item.get("public-key", ""))


class OpenVPNVerifier(OutboundVerifier):
    type_name = "openvpn"
    mihomo_only = True

    def verify_fields(self, item: dict, ctx: VerifyContext) -> bool:
        if not wrap(item.get("ca", "")):
            return False
        if "proto" in item and wrap(item.get("proto", "")).lower() not in OPENVPN_PROTOS:
            return False
        if "cipher" in item and wrap(item.get("cipher", "")).upper() not in OPENVPN_CIPHERS_UPPER:
            return False
        if "auth" in item and wrap(item.get("auth", "")).upper() not in OPENVPN_AUTH:
            return False
        if "comp-lzo" in item and wrap(item.get("comp-lzo", "")) not in OPENVPN_COMP:
            return False

        has_user = bool(wrap(item.get("username", "")) and wrap(item.get("password", "")))
        has_cert = bool(wrap(item.get("cert", "")) and wrap(item.get("key", "")))
        return has_user or has_cert

    def auth_field(self, item: dict) -> str | None:
        if wrap(item.get("password", "")):
            return "password"
        return None

    def duplicate_key(self, item: dict) -> tuple:
        return (
            self.type_name,
            item.get("username", ""),
            item.get("password", ""),
            item.get("cert", ""),
            item.get("key", ""),
        )


class MasqueVerifier(OutboundVerifier):
    type_name = "masque"
    mihomo_only = True

    def verify_fields(self, item: dict, ctx: VerifyContext) -> bool:
        if not wrap(item.get("private-key", "")) or not wrap(item.get("public-key", "")):
            return False
        network = wrap(item.get("network", ""))
        if network not in MASQUE_NETWORKS:
            return False
        return True

    def auth_field(self, item: dict) -> str | None:
        return None

    def duplicate_key(self, item: dict) -> tuple:
        return (self.type_name, item.get("private-key", ""), item.get("public-key", ""))
