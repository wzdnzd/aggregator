# -*- coding: utf-8 -*-

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from config.models import StorageItem, TaskParams
from crawl.models import ChannelResult, CrawlContext
from push import PushTo

TConfig = TypeVar("TConfig")
PLUGINS: dict[str, ScriptPlugin[Any]] = {}


@dataclass
class PluginContext:
    crawl: CrawlContext
    params: dict[str, object]
    task: TaskParams
    persist: StorageItem | dict[str, StorageItem] | None
    pushtool: PushTo | None
    storage_items: dict[str, StorageItem]


class ScriptPlugin(ABC, Generic[TConfig]):
    name: str = ""
    isolate: bool = False

    @abstractmethod
    def parse(self, ctx: PluginContext) -> TConfig:
        raise NotImplementedError

    @abstractmethod
    def run(self, config: TConfig, ctx: PluginContext) -> ChannelResult:
        raise NotImplementedError


def register_plugin(plugin: ScriptPlugin[Any]) -> ScriptPlugin[Any]:
    PLUGINS[plugin.name] = plugin
    return plugin
