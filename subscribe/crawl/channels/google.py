# -*- coding: utf-8 -*-

import re
import time
import urllib.parse

import utils
from config.models import GoogleConfig, TaskParams
from crawl.base import Channel, register_channel
from crawl.helpers import is_reachable
from crawl.models import ChannelResult, CrawlContext
from logger import logger
from origin import Origin


class GoogleChannel(Channel[GoogleConfig]):
    name = "google"

    def crawl(self, config: GoogleConfig, ctx: CrawlContext) -> ChannelResult:
        if not is_reachable("https://www.google.com"):
            logger.warning("[GoogleCrawl] skip because google is unreachable")
            return ChannelResult()
        return crawl_google(config)


def crawl_google(config: GoogleConfig) -> ChannelResult:
    items, query = set(), urllib.parse.quote('"/api/v1/client/subscribe?token="')
    for text in config.exclude_sites or []:
        text = utils.trim(text).lower()
        if text and "+" not in text:
            items.add(urllib.parse.quote(f"-site:{text}"))

    reject = "+".join(list(items))
    if reject:
        query = f"{query}+{reject}"

    num, limits = 100, min(max(1, config.limit), 1000)
    url = f"https://www.google.com/search?q={query}&tbs=qdr:d{max(config.days, 1)}"
    params = {"hl": "zh-CN", "num": num}
    task = TaskParams(push_to=list(config.push_to))
    result = ChannelResult()
    starttime = time.time()

    for start in range(0, limits, num):
        params["start"] = start
        content = re.sub(r"\\\\n", "", utils.http_get(url=url, params=params))
        content = re.sub(r"\?token\\\\u003d", "?token=", content, flags=re.I)
        regex = r'https?://(?:[a-zA-Z0-9_\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9_\u4e00-\u9fa5\-]+(?::\d+)?/?(?:<em(?:\s+)?class="qkunPe">/?)?api/v1/client/subscribe\?token(?:</em>)?=[a-zA-Z0-9]{16,32}'
        subscribes = re.findall(regex, content)
        for link in subscribes:
            link = re.sub(r'<em(?:\s+)?class="qkunPe">|</em>|\s+', "", link).replace("http://", "https://", 1)
            try:
                if config.exclude and re.search(config.exclude, link):
                    continue
                result.add_subscribe(link, Origin.GOOGLE.name, task)
            except Exception:
                continue

        if re.search(
            r'<p aria-level="3" role="heading".*?>\s*找不到和您查询的“\s*<span>\s*.*?/api/v1/client/subscribe\?token=.*?\s*</span>\s*”相符的内容或信息。\s*</p>',
            content,
            flags=re.I,
        ):
            break

    logger.info(
        f"[GoogleCrawl] finished crawl from Google, found {len(result.items)} subscriptions, cost: {time.time() - starttime:.2f}s"
    )
    return result


register_channel(GoogleChannel())
