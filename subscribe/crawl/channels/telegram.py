# -*- coding: utf-8 -*-

import itertools
import re
import time
from dataclasses import replace

import utils
from config.models import TelegramChannelConfig, TelegramConfig
from crawl.base import Channel, register_channel
from crawl.extract import extract_subscribes
from crawl.helpers import is_reachable, merge_results
from crawl.models import ChannelResult, CrawlContext
from logger import logger
from origin import Origin


class TelegramChannel(Channel[TelegramConfig]):
    name = "telegram"

    def crawl(self, config: TelegramConfig, ctx: CrawlContext) -> ChannelResult:
        if not is_reachable("https://t.me"):
            logger.warning("[TelegramCrawl] skip because telegram is unreachable")
            return ChannelResult()
        return crawl_telegram(config, ctx)


def crawl_telegram(config: TelegramConfig, ctx: CrawlContext) -> ChannelResult:
    starttime = time.time()
    params = []
    for name, item in config.channels.items():
        if not item.push_to:
            continue
        exclude = item.exclude
        if config.exclude:
            exclude = f"{exclude}|{config.exclude}".removeprefix("|")
        if exclude != item.exclude:
            item = replace(item, exclude=exclude)
        params.append([name, item, config.pages])
    page_groups = utils.multi_thread_run(func=_telegram_pages, tasks=params, num_threads=ctx.num_threads)
    tasks = list(itertools.chain.from_iterable(page_groups))
    jobs = [[url, item, ctx.include_nodes] for url, item in tasks]
    results = utils.multi_thread_run(func=_crawl_telegram_page, tasks=jobs, num_threads=ctx.num_threads)
    result = merge_results(results)
    logger.info(
        f"[TelegramCrawl] finished crawl from Telegram, found {len(result.items)} subscriptions, cost: {time.time() - starttime:.2f}s"
    )
    return result


def _telegram_pages(channel: str, config: TelegramChannelConfig, pages: int) -> list[list]:
    if pages <= 1:
        return [[f"https://t.me/s/{channel}", config]]

    count = get_telegram_pages(channel=channel)
    if count == 0:
        return []

    arrays = range(count, -1, -100)
    pages = min(pages, len(arrays))
    return [[f"https://t.me/s/{channel}?before={item}", config] for item in arrays[:pages]]


def get_telegram_pages(channel: str) -> int:
    if not channel or not channel.strip():
        return 0

    url = f"https://t.me/s/{channel}"
    content = utils.http_get(url=url)
    before = 0
    try:
        regex = rf'<link\s+rel="canonical"\s+href="/s/{channel}\?before=(\d+)">'
        groups = re.findall(regex, content)
        before = int(groups[0]) if groups else before
    except Exception:
        logger.error(f"[CrawlError] cannot count page num, chanel: {channel}")
    return before


def _crawl_telegram_page(url: str, config: TelegramChannelConfig, include_nodes: bool) -> ChannelResult:
    if not url or not config.push_to:
        return ChannelResult()
    content = utils.http_get(url=url)
    if not content:
        return ChannelResult()
    return extract_subscribes(
        content=content,
        push_to=config.push_to,
        include=config.include,
        exclude=config.exclude,
        source=Origin.TELEGRAM.name,
        task=config.task,
        reversed=True,
        include_nodes=include_nodes,
    )


register_channel(TelegramChannel())
