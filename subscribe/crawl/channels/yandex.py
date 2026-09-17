# -*- coding: utf-8 -*-

import re
import time
import urllib.parse

import utils
from config.models import TaskParams, YandexConfig
from crawl.base import Channel, register_channel
from crawl.helpers import is_reachable
from crawl.models import ChannelResult, CrawlContext
from logger import logger
from origin import Origin


class YandexChannel(Channel[YandexConfig]):
    name = "yandex"

    def crawl(self, config: YandexConfig, ctx: CrawlContext) -> ChannelResult:
        if not is_reachable("https://yandex.com"):
            logger.warning("[YandexCrawl] skip because yandex is unreachable")
            return ChannelResult()
        return crawl_yandex(config)


def crawl_yandex(config: YandexConfig) -> ChannelResult:
    reject, query = "", urllib.parse.quote("/api/v1/client/subscribe?token=")
    if config.exclude_sites:
        items = list(set([re.escape(utils.trim(item).lower()) for item in config.exclude_sites if utils.trim(item)]))
        reject = "|".join(items)

    url = f'https://yandex.com/search/?text="{query}"&lr=10599&cee=1'
    if config.days > 0:
        url = f"{url}&within={config.days}"

    starttime = time.time()
    headers = {
        "User-Agent": utils.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip",
    }

    content = utils.http_get(url=url, headers=headers)
    pages = max(1, config.pages)
    if content:
        regex = r'<a class="VanillaReact Pager-Item Pager-Item_type_page" href=".*?" aria-label="Page \d+".*?>(\d+)</a>'
        groups = re.findall(regex, content, flags=re.I)
        if groups:
            pages = min(pages, max([int(item) for item in groups]))

    task = TaskParams(push_to=list(config.push_to))
    result = ChannelResult()
    for page in range(0, pages):
        content = utils.http_get(url=f"{url}&p={page}", headers=headers)
        if not content:
            logger.error(f"[YandexCrawl] cannot get content from page: {page}")
            continue

        groups = re.findall(r"<li class=\"serp-item\s+serp-item_card\s?\".*?>([\s\S]*?)</li>", content)
        if not groups:
            logger.error(f"[YandexCrawl] cannot get any search result from page: {page}")
            continue

        for group in groups:
            try:
                if reject:
                    regex = r'<div class="Path Organic-Path path organic__path"><a .*?href="(.*?)".*?>.*?</a></div>'
                    link = re.findall(regex, group, flags=re.I)[0]
                    if re.search(reject, link):
                        continue
            except Exception:
                logger.error(f"[YandexCrawl] invalid regex pattern: {reject}")
                continue

            regex = r"https?://(?:[a-zA-Z0-9_\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9_\u4e00-\u9fa5\-]+(?::\d+)?/<b>api</b>/<b>v</b><b>1</b>/<b>client</b>/<b>subscribe</b>\?<b>token</b>=[a-zA-Z0-9]{16,32}"
            links = re.findall(regex, group, flags=re.I)
            for link in links:
                try:
                    link = re.sub(r"<b>|</b>", "", link).replace("http://", "https://")
                    if config.exclude and re.search(config.exclude, link):
                        continue
                    result.add_subscribe(link, Origin.YANDEX.name, task)
                except Exception:
                    continue

    logger.info(
        f"[YandexCrawl] finished crawl from Yandex, found {len(result.items)} subscriptions, cost: {time.time() - starttime:.2f}s"
    )
    return result


register_channel(YandexChannel())
