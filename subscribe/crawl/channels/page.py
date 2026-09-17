# -*- coding: utf-8 -*-

from __future__ import annotations

from copy import deepcopy

import utils
from config.models import PageJob, TaskParams
from crawl.base import Channel, register_channel
from crawl.extract import extract_subscribes
from crawl.models import ChannelResult, CrawlContext
from logger import logger
from origin import Origin
from urlvalidator import isurl


class PageChannel(Channel[list[PageJob]]):
    name = "pages"

    def __init__(
        self,
        url: str = "",
        include: str = "",
        exclude: str = "",
        push_to: list[str] | None = None,
        task: TaskParams | None = None,
        headers: dict[str, str] | None = None,
        origin: str = Origin.PAGE.name,
        skip_cache: bool = False,
    ) -> None:
        self.url = utils.trim(url)
        self.include = include
        self.exclude = exclude
        self.push_to = list(push_to or [])
        self.task = task or TaskParams(push_to=self.push_to)
        self.headers = headers
        self.origin = origin or Origin.PAGE.name
        self.skip_cache = skip_cache

    def crawl(self, config: list[PageJob], ctx: CrawlContext) -> ChannelResult:
        from crawl.helpers import fetch_jobs

        jobs = []
        for job in config:
            if not job.enable or not job.push_to:
                continue
            for url in job.expand_urls():
                jobs.append(
                    PageChannel(
                        url=url,
                        include=job.include,
                        exclude=job.exclude,
                        push_to=job.push_to,
                        task=job.task,
                        headers=job.headers,
                        origin=job.origin,
                        skip_cache=job.skip_cache,
                    )
                )
        return fetch_jobs(jobs, ctx)

    def fetch(self, ctx: CrawlContext, url: str | None = None) -> ChannelResult:
        target = utils.trim(url or self.url)
        if not target or not isurl(target):
            logger.error(f"[PageCrawl] cannot crawl from page: {target}")
            return ChannelResult()
        headers = deepcopy(self.headers) if self.headers else None
        content = utils.http_get(url=target, headers=headers)
        if not content:
            return ChannelResult()
        return extract_subscribes(
            content=content,
            push_to=self.push_to,
            include=self.include,
            exclude=self.exclude,
            source=self.origin,
            task=self.task,
            skip_cache=self.skip_cache,
            include_nodes=ctx.include_nodes,
        )

    def fetch_many(self, ctx: CrawlContext, urls: list[str] | None = None) -> ChannelResult:
        from crawl.helpers import merge_results

        targets = urls if urls is not None else ([self.url] if self.url else [])
        targets = [utils.trim(item) for item in targets if utils.trim(item)]
        if not targets:
            return ChannelResult()
        if len(targets) == 1:
            return self.fetch(ctx, url=targets[0])
        results = utils.multi_thread_run(
            func=self.fetch,
            tasks=[[ctx, link] for link in targets],
            num_threads=ctx.num_threads,
            show_progress=ctx.display,
        )
        return merge_results(results)


register_channel(PageChannel())
