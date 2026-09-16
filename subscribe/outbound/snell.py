# -*- coding: utf-8 -*-

from __future__ import annotations

import utils

from outbound.base import OutboundVerifier, VerifyContext
from outbound.common import wrap

SNELL_OBFS_MODES = ("", "http", "tls", "shadow-tls", "restls", "jls")


class SnellVerifier(OutboundVerifier):
    type_name = "snell"

    def verify_fields(self, item: dict, ctx: VerifyContext) -> bool:
        if "version" in item and not utils.is_number(item["version"]):
            return False

        version = int(item.get("version", 1))
        if version < 1 or version > 5:
            return False

        # v1/v2 do not support UDP; v3/v4/v5 do
        if version < 3:
            item.pop("udp", None)

        if "obfs-opts" not in item:
            return True

        obfs_opts = item.get("obfs-opts", {})
        if not obfs_opts or type(obfs_opts) != dict:
            return False
        if "mode" not in obfs_opts:
            return True

        mode = wrap(obfs_opts.get("mode", ""))
        return mode in SNELL_OBFS_MODES

    def auth_field(self, item: dict) -> str | None:
        return "psk"
