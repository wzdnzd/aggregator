# -*- coding: utf-8 -*-

from config.models import ScriptJob
from crawl.base import Channel, register_channel
from crawl.channels.plugins import PLUGINS, PluginContext
from crawl.models import ChannelResult, CrawlContext
from logger import logger


class ScriptChannel(Channel[list[ScriptJob]]):
    name = "scripts"

    def crawl(self, config: list[ScriptJob], ctx: CrawlContext) -> ChannelResult:
        merged = ChannelResult()

        if not isinstance(ctx, CrawlContext):
            return merged
        storage_items = ctx.storage.items if ctx.storage is not None else {}
        for job in config:
            if not isinstance(job, ScriptJob) or not job.enable:
                continue
            plugin = PLUGINS.get(job.plugin)
            if plugin is None:
                continue
            persist = None
            if isinstance(job.persist, str):
                persist = storage_items.get(job.persist)
            elif isinstance(job.persist, dict):
                resolved = {}
                for key, value in job.persist.items():
                    resolved[key] = storage_items.get(value) if isinstance(value, str) else value
                persist = resolved
            pctx = PluginContext(
                crawl=ctx,
                params=job.options,
                task=job.task,
                persist=persist,
                pushtool=ctx.pushtool,
                storage_items=storage_items,
            )
            try:
                parsed = plugin.parse(pctx)
                merged.merge(plugin.run(parsed, pctx))
            except Exception as exc:
                logger.error(f"[ScriptError] plugin {job.plugin} failed: {exc}")
        return merged


register_channel(ScriptChannel())
