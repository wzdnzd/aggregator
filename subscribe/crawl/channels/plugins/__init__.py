# -*- coding: utf-8 -*-

from importlib import import_module

from .base import PLUGINS, PluginContext

for _name in (
    "dynamic",
    "fofa",
    "gitforks",
    "scaner",
    "tempairport",
    "v2rayfree",
    "v2rayse",
):
    import_module(f"{__name__}.{_name}")

__all__ = ["PLUGINS", "PluginContext"]
