# -*- coding: utf-8 -*-

from __future__ import annotations

import base64
import re

import utils
from outbound.base import OutboundVerifier, VerifyContext

COMMON_SS_SUPPORTED_CIPHERS = [
    "aes-128-gcm",
    "aes-192-gcm",
    "aes-256-gcm",
    "aes-128-cfb",
    "aes-192-cfb",
    "aes-256-cfb",
    "aes-128-ctr",
    "aes-192-ctr",
    "aes-256-ctr",
    "rc4-md5",
    "chacha20-ietf",
    "xchacha20",
    "chacha20-ietf-poly1305",
    "xchacha20-ietf-poly1305",
]

# reference: https://github.com/SagerNet/sing-shadowsocks2/blob/dev/shadowaead_2022/method.go
MIHOMO_SS_SUPPORTED_CIPHERS_SALT_LEN = {
    "2022-blake3-aes-128-gcm": 16,
    "2022-blake3-aes-256-gcm": 32,
    "2022-blake3-chacha20-poly1305": 32,
}

MIHOMO_SS_SUPPORTED_CIPHERS = (
    COMMON_SS_SUPPORTED_CIPHERS
    + list(MIHOMO_SS_SUPPORTED_CIPHERS_SALT_LEN.keys())
    + [
        "aes-128-ccm",
        "aes-192-ccm",
        "aes-256-ccm",
        "aes-128-gcm-siv",
        "aes-256-gcm-siv",
        "chacha20",
        "chacha8-ietf-poly1305",
        "xchacha8-ietf-poly1305",
        "lea-128-gcm",
        "lea-192-gcm",
        "lea-256-gcm",
        "rabbit128-poly1305",
        "aegis-128l",
        "aegis-256",
        "aez-384",
        "deoxys-ii-256-128",
        "none",
    ]
)

SSR_SUPPORTED_CIPHERS = COMMON_SS_SUPPORTED_CIPHERS + ["dummy", "none"]
SSR_SUPPORTED_OBFS = [
    "plain",
    "http_simple",
    "http_post",
    "random_head",
    "tls1.2_ticket_auth",
    "tls1.2_ticket_fastauth",
]
SSR_SUPPORTED_PROTOCOL = [
    "origin",
    "auth_sha1_v4",
    "auth_aes128_md5",
    "auth_aes128_sha1",
    "auth_chain_a",
    "auth_chain_b",
]

CLASH_SS_PLUGINS = ("", "obfs", "v2ray-plugin")
MIHOMO_SS_PLUGINS = CLASH_SS_PLUGINS + ("shadow-tls", "restls", "gost-plugin", "kcptun", "jls")


def verify_ss_2022_password(cipher: str, password: str) -> bool:
    password = utils.trim(password)
    if not password:
        return False

    words = password.split(":")
    if cipher == "2022-blake3-chacha20-poly1305" and len(words) > 1:
        return False

    key_len = MIHOMO_SS_SUPPORTED_CIPHERS_SALT_LEN.get(cipher)
    if not key_len:
        return False

    for word in words:
        if not word or not re.fullmatch(r"[A-Za-z0-9+/]+=*$", word) or len(word) % 4 != 0:
            return False
        try:
            text = base64.b64decode(word, validate=True)
        except Exception:
            return False
        if len(text) != key_len:
            return False

    return True


class ShadowsocksVerifier(OutboundVerifier):
    type_name = "ss"

    def verify_fields(self, item: dict[str, object], ctx: VerifyContext) -> bool:
        ciphers = MIHOMO_SS_SUPPORTED_CIPHERS if ctx.is_mihomo else COMMON_SS_SUPPORTED_CIPHERS
        if item.get("cipher") not in ciphers:
            return False

        if item["cipher"] in MIHOMO_SS_SUPPORTED_CIPHERS_SALT_LEN:
            if not verify_ss_2022_password(item["cipher"], str(item.get("password", ""))):
                return False

        plugin = item.get("plugin", "")
        plugins = MIHOMO_SS_PLUGINS if ctx.is_mihomo else CLASH_SS_PLUGINS
        if plugin not in plugins:
            return False
        if not plugin:
            return True

        plugin_opts = item.get("plugin-opts", {})
        if plugin_opts in (None, ""):
            plugin_opts = {}
        if type(plugin_opts) != dict:
            return False

        mode = plugin_opts.get("mode", "")
        if plugin == "jls":
            return all(utils.trim(str(plugin_opts.get(k, ""))) for k in ("host", "username", "password"))
        if plugin == "restls":
            return all(utils.trim(str(plugin_opts.get(k, ""))) for k in ("host", "password", "version-hint"))
        if plugin == "shadow-tls":
            return bool(utils.trim(str(plugin_opts.get("host", ""))))
        if plugin == "kcptun":
            return True
        if plugin == "obfs":
            return mode in ("tls", "http")
        if plugin in ("v2ray-plugin", "gost-plugin"):
            return mode == "websocket"
        return False


class ShadowsocksRVerifier(OutboundVerifier):
    type_name = "ssr"

    def verify_fields(self, item: dict[str, object], ctx: VerifyContext) -> bool:
        if item.get("cipher") not in SSR_SUPPORTED_CIPHERS:
            return False
        if item.get("obfs") not in SSR_SUPPORTED_OBFS:
            return False
        if item.get("protocol") not in SSR_SUPPORTED_PROTOCOL:
            return False
        return True

    def duplicate_key(self, item: dict[str, object]) -> tuple[str, object]:
        return (self.type_name, str(item.get("protocol-param", "")).lower())
