# -*- coding: utf-8 -*-

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from crawl.models import ChannelResult, CrawlContext

TConfig = TypeVar("TConfig")

CHANNELS: dict[str, Channel[Any]] = {}


class Channel(ABC, Generic[TConfig]):
    name: str = ""

    @abstractmethod
    def crawl(self, config: TConfig, ctx: CrawlContext) -> ChannelResult:
        raise NotImplementedError


def register_channel(channel: Channel[Any]) -> Channel[Any]:
    CHANNELS[channel.name] = channel
    return channel
