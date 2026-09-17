# -*- coding: utf-8 -*-

import itertools
import json
import os
import re
import time
import traceback

import utils
from config.models import GithubConfig
from crawl.base import Channel, register_channel
from crawl.channels.page import PageChannel
from crawl.models import ChannelResult, CrawlContext
from logger import logger
from origin import Origin


class GithubChannel(Channel[GithubConfig]):
    name = "github"

    def crawl(self, config: GithubConfig, ctx: CrawlContext) -> ChannelResult:
        return crawl_github(config, ctx)


def intercept(text: str, excludes: list[str] | None = None) -> bool:
    if not excludes:
        return False
    for regex in excludes:
        try:
            if re.search(regex, text, flags=re.I):
                return True
        except Exception:
            logger.error(f"[GithubRepoIntercept] invalid regex pattern: {regex}")
    return False


def paging(start: int, end: int, peer_page: int) -> list[int]:
    if start > end or peer_page <= 0:
        return []
    pages = []
    for i in range(start, end + 1, peer_page):
        pages.append(i // peer_page + 1)
    return pages


def search_github(page: int, cookie: str, searchtype: str, sortedby: str) -> str:
    if page <= 0 or utils.isblank(cookie):
        return ""

    searchtype = "Code" if utils.isblank(searchtype) else searchtype
    sortedby = "indexed" if utils.isblank(sortedby) else sortedby
    query = "%22%2Fapi%2Fv1%2Fclient%2Fsubscribe%3Ftoken%3D%22"
    if searchtype.lower() == "code":
        query = "%2F%5C%2Fapi%5C%2Fv1%5C%2Fclient%5C%2Fsubscribe%5C%3Ftoken%3D%5Ba-zA-Z0-9%5D%7B8%2C32%7D%2F"

    url = f"https://github.com/search?o=desc&p={page}&q={query}&s={sortedby}&type={searchtype}"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Referer": "https://github.com",
        "User-Agent": utils.USER_AGENT,
        "Cookie": f"user_session={cookie}",
    }
    content = utils.http_get(url=url, headers=headers)
    if re.search(r"<h1>Sign in to GitHub</h1>", content, flags=re.I):
        logger.error("[GithubCrawl] session has expired, please provide a valid session and try again")
        return ""
    return content


def search_github_issues(page: int, cookie: str) -> list[str]:
    content = search_github(page=page, cookie=cookie, searchtype="Issues", sortedby="created")
    if utils.isblank(content):
        return []
    try:
        groups = re.findall(r'href="(/.*/.*/issues/\d+)">', content, flags=re.I)
        return [f"https://github.com{item}" for item in list(set(groups))]
    except Exception:
        return []


def search_github_issues_byapi(peer_page: int = 50, page: int = 1) -> list[str]:
    peer_page, page = min(max(peer_page, 1), 100), max(1, page)
    url = f"https://api.github.com/search/issues?q=%22%2Fapi%2Fv1%2Fclient%2Fsubscribe%3Ftoken%3D%22&sort=created&order=desc&per_page={peer_page}&page={page}"
    content = utils.http_get(url=url)
    if utils.isblank(content):
        return []
    try:
        items, links = json.loads(content).get("items", []), set()
        for item in items:
            link = item.get("html_url", "")
            if link:
                links.add(link)
        return list(links)
    except Exception:
        logger.error("[GithubIssuesCrawl] occur error when search issues from github")
        traceback.print_exc()
        return []


def search_github_code_byapi(
    token: str, peer_page: int = 50, page: int = 1, excludes: list[str] | None = None
) -> list[str]:
    if utils.isblank(token):
        return []

    peer_page, page = min(max(peer_page, 1), 100), max(1, page)
    url = f"https://api.github.com/search/code?q=%22%2Fapi%2Fv1%2Fclient%2Fsubscribe%3Ftoken%3D%22&sort=indexed&order=desc&per_page={peer_page}&page={page}"
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"}
    content = utils.http_get(url=url, headers=headers)
    if utils.isblank(content):
        return []
    try:
        items = json.loads(content).get("items", [])
        links = set()
        excludes = list(set(excludes or []))
        for item in items:
            if not item or not isinstance(item, dict):
                continue
            link = item.get("html_url", "")
            if not link:
                continue
            reponame = item.get("repository", {}).get("full_name", "") + "/"
            if not intercept(text=reponame, excludes=excludes):
                links.add(link)
        return list(links)
    except Exception:
        return []


def search_github_code(page: int, cookie: str, excludes: list[str] | None = None) -> list[str]:
    content = search_github(page=page, cookie=cookie, searchtype="Code", sortedby="indexed")
    if utils.isblank(content):
        return []
    try:
        groups = re.findall(r'href="(/[^\s"]+/blob/(?:[^"]+)?)#L\d+"', content, flags=re.I)
        uris = list(set(groups)) if groups else []
        links = set()
        excludes = list(set(excludes or []))
        for uri in uris:
            if not intercept(text=uri, excludes=excludes):
                links.add(f"https://github.com{uri}")
        return list(links)
    except Exception:
        return []


def crawl_github(config: GithubConfig, ctx: CrawlContext) -> ChannelResult:
    cookie = os.environ.get("GH_COOKIE", "").strip()
    token = os.environ.get("GH_TOKEN", "").strip()
    if utils.isblank(cookie) and utils.isblank(token):
        logger.error("[GithubCrawl] cannot start crawl from github because cookie and token is missing")
        return ChannelResult()

    links, starttime = [], time.time()
    method = "search on the page" if utils.isblank(token) else "rest api"
    excludes = config.exclude_repos or []

    if utils.isblank(token):
        pages = [item for item in range(1, config.pages + 1)] * 2
        params = [[item, cookie, excludes] for item in pages]
        results = utils.multi_thread_run(func=search_github_code, tasks=params, num_threads=ctx.num_threads)
        links.extend(list(set(itertools.chain.from_iterable(results))))
        links.extend(search_github_issues(page=1, cookie=cookie))
    else:
        peer_page, count = 50, 10
        pages = paging(start=1, end=config.pages * count, peer_page=peer_page)
        params = [[token, peer_page, item, excludes] for item in pages] * 2
        results = utils.multi_thread_run(func=search_github_code_byapi, tasks=params, num_threads=ctx.num_threads)
        links.extend(list(set(itertools.chain.from_iterable(results))))
        links.extend(search_github_issues_byapi(peer_page=5, page=1))

    page = PageChannel(
        include="",
        exclude=config.exclude,
        push_to=config.push_to,
        origin=Origin.GITHUB.name,
    )
    result = page.fetch_many(ctx, urls=list(dict.fromkeys(links)))
    logger.info(
        f"[GithubCrawl] finished crawl from Github through {method}, found {len(result.items)} subscriptions need check, cost: {time.time() - starttime:.2f}s"
    )
    return result


register_channel(GithubChannel())
