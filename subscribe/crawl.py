# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import base64
import gzip
import importlib
import itertools
import json
import multiprocessing
import os
import random
import re
import socket
import ssl
import string
import sys
import time
import traceback
import typing
import urllib
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from dataclasses import dataclass
from functools import cache
from multiprocessing.managers import ListProxy
from multiprocessing.synchronize import Semaphore

import airport
import push
import utils
import workflow
import yaml
from logger import logger
from origin import Origin
from urlvalidator import isurl
from yaml.constructor import ConstructorError

SEPARATOR = "-"


@dataclass
class ValidateResult(object):
    # single node collections
    proxies: set = None

    # valid subscription
    available: dict = None

    # valid or to be observed
    potential: dict = None

    # unknown
    unknown: str = None


SINGLE_LINK_FLAG = "singlelink://"

# environment key
SINGLE_PROXIES_ENV_NAME = "ALLOW_SINGLE_LINK"


@cache
def allow_single_link() -> bool:
    """whether to allow crawling a single proxy link"""
    return os.environ.get(SINGLE_PROXIES_ENV_NAME, "").lower() == "true"


def multi_thread_crawl(func: typing.Callable, params: list) -> dict:
    if not func or not params or type(params) != list:
        return {}

    # concurrent run
    results = utils.multi_thread_run(func=func, tasks=params)

    funcname = getattr(func, "__name__", repr(func)).replace("_", "-")
    tasks, uri = {}, f"{SINGLE_LINK_FLAG}{funcname}"

    for r in results:
        for k, v in r.items():
            k = uri if k == SINGLE_LINK_FLAG else k
            item = tasks.get(k, {})
            item["origin"] = v.pop("origin", item.get("origin", ""))
            pts = item.get("push_to", [])
            pts.extend(v.pop("push_to", []))
            item["push_to"] = list(set(pts))

            # merge proxies link
            if k.startswith(SINGLE_LINK_FLAG):
                newproxies = v.pop("proxies", [])
                if newproxies and type(newproxies) == list:
                    oldproxies = item.get("proxies", [])
                    oldproxies.extend(newproxies)
                    item["proxies"] = list(set(oldproxies))

            item.update(v)
            tasks[k] = item

    return tasks


def batch_crawl(conf: dict, num_threads: int = 50, display: bool = True) -> list[dict]:
    mode, connectable = crawlable()

    if not conf or not conf.get("enable", True):
        # only crawl if mode == 1
        if mode == 1:
            logger.warning(f"exit process because mode=1 and crawling task is disabled")
            sys.exit(0)

        else:
            return []

    datasets, peristedtasks = [], {}
    try:
        persists = conf.get("persist", {})
        engine = persists.get("engine", "")
        subspushconf = persists.get("subs", {})
        linkspushconf = persists.get("proxies", {})

        pushtool = push.get_instance(engine=engine)
        should_persist = pushtool.validate(push_conf=subspushconf)
        # skip tasks if mode == 1 and not set persistence
        if mode == 1 and not should_persist:
            logger.warning(
                f"[CrawlWarn] skip crawling tasks because the mode is set to crawl only but no valid persistence configuration is set"
            )
            sys.exit(0)

        # allow if persistence configuration is valid
        enable = conf.get("singlelink", False)
        allow = enable and pushtool.validate(linkspushconf)

        # save it to environment
        os.environ[SINGLE_PROXIES_ENV_NAME] = str(allow).lower()

        records, threshold = {}, conf.get("threshold", 1)

        if connectable:
            # Google
            google_spider = conf.get("google", {})
            if google_spider:
                push_to = google_spider.get("push_to", [])
                exclude = google_spider.get("exclude", "")
                notinurl = google_spider.get("notinurl", [])
                qdr = int(google_spider.get("qdr", 7))
                limits = int(google_spider.get("limits", 100))
                records.update(
                    crawl_google(
                        qdr=qdr,
                        push_to=push_to,
                        exclude=exclude,
                        limits=limits,
                        notinurl=notinurl,
                    )
                )

            # yanex
            yandex_spider = conf.get("yandex", {})
            if yandex_spider:
                push_to = yandex_spider.get("push_to", [])
                exclude = yandex_spider.get("exclude", "")
                notinurl = yandex_spider.get("notinurl", [])
                within = int(yandex_spider.get("within", 2))
                pages = int(yandex_spider.get("pages", 5))
                records.update(
                    crawl_yandex(
                        within=within,
                        push_to=push_to,
                        exclude=exclude,
                        pages=pages,
                        notinurl=notinurl,
                    )
                )

            # Telegram
            telegram_spider = conf.get("telegram", {})
            if telegram_spider and telegram_spider.get("users", {}):
                users = telegram_spider.get("users")
                pages = max(telegram_spider.get("pages", 1), 1)
                records.update(crawl_telegram(users=users, pages=pages))

            # Twitter
            twitter_spider = conf.get("twitter", {})
            if twitter_spider:
                records.update(crawl_twitter(tasks=twitter_spider))

        # skip crawl if mode == 2
        if mode != 2:
            # Github
            github_spider = conf.get("github", {})
            if github_spider and github_spider.get("push_to", []):
                push_to = github_spider.get("push_to")
                pages = github_spider.get("pages", 1)
                exclude = github_spider.get("exclude", "")
                spams = github_spider.get("spams", [])
                records.update(crawl_github(limits=pages, push_to=push_to, exclude=exclude, spams=spams))

            # Github Repository
            repositories = conf.get("repositories", {})
            if repositories:
                records.update(crawl_github_repo(repos=repositories))

            # Page
            pages = conf.get("pages", {})
            if pages:
                records.update(crawl_pages(pages=pages, origin=Origin.PAGE.name))

            # Scripts
            scripts = conf.get("scripts", {})
            if scripts:
                items = batch_call(scripts)
                if items:
                    for item in items:
                        if not item or type(item) != dict:
                            continue

                        if item.get("saved", False):
                            datasets.append(item)
                            continue

                        task = deepcopy(item)
                        subs = task.pop("sub", None)
                        checked = task.pop("checked", True)
                        if type(subs) not in [str, list]:
                            continue
                        if type(subs) == str:
                            subs = [subs]
                        for sub in subs:
                            if utils.isblank(sub):
                                continue

                            if checked:
                                remark(source=task, defeat=0, discovered=True)
                                peristedtasks[sub] = task
                            else:
                                records.update({sub: task})

        # remain
        if should_persist:
            url = pushtool.raw_url(push_conf=subspushconf)
            try:
                url, content = url or "", ""
                if not url.startswith(utils.FILEPATH_PROTOCAL):
                    content = utils.http_get(url=url)
                else:
                    file = url.sub[len(utils.FILEPATH_PROTOCAL) - 1 :]
                    if os.path.exists(file) and os.path.isfile(file):
                        with open(file, "r", encoding="UTF8") as f:
                            content = f.read()

                if not utils.isblank(content):
                    oldsubs = json.loads(content)

                    # tasks.update(oldsubs)
                    for k, v in oldsubs.items():
                        merged = dict(list(v.items()) + list(records.get(k, {}).items()))
                        records[k] = merged
            except:
                logger.error("[CrawlError] load old subscriptions from remote error")
                pass

        if not records:
            if peristedtasks and should_persist and mode != 2:
                content = json.dumps(peristedtasks)
                pushtool.push_to(content=content, push_conf=subspushconf, group="crawl")

            logger.debug("[CrawlInfo] cannot found any subscribe from Google/Telegram/Github and Page with crawler")
            return datasets

        exclude = conf.get("exclude", "")
        taskconf = conf.get("config", {})

        # dedup by token
        tokens = {utils.parse_token(k): k for k in records.keys()}
        tasks = {k: records[k] for k in tokens.values()}

        time.sleep(random.randint(1, 3))

        proxiesconf, jobs = {}, []
        for key, value in tasks.items():
            for k, v in taskconf.items():
                if k not in value:
                    value[k] = v

            jobs.append([key, value, mode, connectable, exclude, threshold])

            # generate single link's configuration
            if key.startswith(SINGLE_LINK_FLAG):
                proxiesconf.update(value)

        availables, unknowns, potentials, proxylinks = [], [], {}, set()
        results = utils.multi_thread_run(func=validate, tasks=jobs, num_threads=num_threads, show_progress=display)
        for result in results:
            if result.available:
                availables.append(result.available)
            if result.potential:
                potentials.update(result.potential)
            if result.proxies:
                proxylinks.update(result.proxies)
            if result.unknown:
                unknowns.append(result.unknown)

        datasets.extend(availables)
        peristedtasks.update(potentials)

        if allow_single_link():
            proxies = list(proxylinks)
            logger.info(f"[CrawlInfo] crawl finished, found {len(proxies)} proxy links")

            if len(proxies) > 0:
                try:
                    content = base64.b64encode("\n".join(proxies).encode()).decode()
                    success = pushtool.push_to(content=content, push_conf=linkspushconf, group="proxies")
                    if success:
                        singlelink = pushtool.raw_url(push_conf=linkspushconf)
                        item = {
                            "name": "singlelink",
                            "sub": singlelink,
                            "debut": True,
                        }
                        item.update(proxiesconf)
                        datasets.append(item)
                except:
                    logger.error("[CrawlError] base64 encode error for proxies links")

        if len(unknowns) > 0:
            unknowns = [utils.mask(url=x) for x in unknowns]
            logger.warning(
                f"[CrawlWarn] some links were found, but could not be confirmed to work, subscriptions: {unknowns}"
            )

        logger.info(f"[CrawlInfo] crawl finished, found {len(datasets)} subscriptions")

        if mode != 2 and should_persist and peristedtasks:
            survivors = {k: v for k, v in peristedtasks.items() if not v.pop("nocache", False)}

            total, rest = len(peristedtasks), len(survivors)
            logger.info(
                f"[CrawlInfo] to be saved subscriptions filtering completed, total: {total}, discard: {total - rest}, rest: {rest}"
            )

            if rest:
                content = json.dumps(survivors)
                pushtool.push_to(content=content, push_conf=subspushconf, group="crawl")
    except:
        logger.error("[CrawlError] crawl from web error")
        traceback.print_exc()

    # only crawl if mode == 1
    if mode == 1:
        logger.warning(f"skip aggregate and exit process because mode=1 represents only crawling subscriptions")
        sys.exit(0)

    return datasets


def crawlable() -> tuple[int, bool]:
    # 0: crawl and aggregate | 1: crawl only | 2: aggregate only
    mode = os.environ.get("WORKFLOW_MODE", "0")
    mode = 0 if not mode.isdigit() else min(max(int(mode), 0), 2)

    reachable = os.environ.get("REACHABLE", "true") in ["true", "1"]
    runnable = False if mode == 2 else reachable

    return mode, runnable


def generate_telegram_task(channel: str, config: dict, pages: int, limits: int) -> list[list]:
    include = config.get("include", "")
    exclude = config.get("exclude", "").strip()
    pts = config.get("push_to", [])
    params = config.get("config", {})
    if pages <= 1:
        return [[f"https://t.me/s/{channel}", pts, include, exclude, limits, params]]

    count = get_telegram_pages(channel=channel)
    if count == 0:
        return []

    arrays = range(count, -1, -100)
    pages = min(pages, len(arrays))
    return [[f"https://t.me/s/{channel}?before={x}", pts, include, exclude, limits, params] for x in arrays[:pages]]


def crawl_telegram_page(
    url: str,
    pts: list,
    include: str = "",
    exclude: str = "",
    limits: int = 25,
    config: dict = {},
) -> dict:
    if not url or not pts:
        return {}

    limits = max(1, limits)
    content = utils.http_get(url=url)
    if not content:
        return {}

    return extract_subscribes(
        content=content,
        push_to=pts,
        include=include,
        limits=limits,
        source=Origin.TELEGRAM.name,
        exclude=exclude,
        config=config,
        reversed=True,
    )


def crawl_telegram(users: dict, pages: int = 1, limits: int = 3) -> dict:
    if not users:
        return {}

    pages, limits = max(pages, 1), max(1, limits)
    starttime = time.time()

    params = [[k, v, pages, limits] for k, v in users.items()]
    results = utils.multi_thread_run(func=generate_telegram_task, tasks=params)

    tasks = list(itertools.chain.from_iterable(results))
    subscribes = multi_thread_crawl(func=crawl_telegram_page, params=tasks)
    cost = "{:.2f}s".format(time.time() - starttime)
    logger.info(f"[TelegramCrawl] finished crawl from Telegram, found {len(subscribes)} subscriptions, cost: {cost}")
    return subscribes


def crawl_single_repo(username: str, repo: str, push_to: list = [], limits: int = 5, exclude: str = "") -> dict:
    if not username or not repo:
        logger.error(f"cannot crawl from github, username: {username}\trepo: {repo}")
        return {}

    # 列出repo所有文件名
    # url = f"https://api.github.com/repos/{username}/{repo}/contents/"

    # 列出repo commit记录
    limits = max(1, limits)
    url = f"https://api.github.com/repos/{username.strip()}/{repo.strip()}/commits?per_page={limits}"

    content = utils.http_get(url=url)
    if content == "":
        return {}

    try:
        commits = json.loads(content)
        collections = {}
        for item in commits:
            content = utils.http_get(url=item.get("url", ""))
            if not content:
                continue
            commit = json.loads(content)
            files = commit.get("files", [])
            for file in files:
                patch = file.get("patch", "")
                collections.update(
                    extract_subscribes(
                        content=patch,
                        push_to=push_to,
                        source=Origin.REPO.name,
                        exclude=exclude,
                    )
                )
        return collections
    except:
        logger.error(f"[GithubCrawl] crawl from github error, username: {username}\trepo: {repo}")
        return {}


def crawl_github_repo(repos: dict) -> list[dict]:
    if not repos:
        return {}
    params = []

    starttime = time.time()
    for _, v in repos.items():
        username = v.get("username", "").strip()
        repo_name = v.get("repo_name", "").strip()
        push_to = v.get("push_to", [])
        limits = max(v.get("commits", 2), 1)
        exclude = v.get("exclude", "").strip()

        if not username or not repo_name or not push_to:
            continue
        params.append([username, repo_name, push_to, limits, exclude])

    subscribes = multi_thread_crawl(func=crawl_single_repo, params=params)
    cost = "{:.2f}s".format(time.time() - starttime)
    logger.info(f"[RepoCrawl] finished crawl from Repositorie, found {len(subscribes)} subscriptions, cost: {cost}")
    return subscribes


def crawl_google(
    qdr: int = 10,
    push_to: list = [],
    exclude: str = "",
    limits: int = 100,
    interval: int = 0,
    notinurl: list = [],
) -> dict:
    items, query = set(), urllib.parse.quote('"/api/v1/client/subscribe?token="')
    if notinurl and type(notinurl) == list:
        for text in notinurl:
            text = utils.trim(text).lower()
            if text and "+" not in text:
                items.add(urllib.parse.quote(f"-site:{text}"))

    reject = "+".join(list(items))
    if reject:
        # not search from some site, see: https://zhuanlan.zhihu.com/p/136076792
        query = f"{query}+{reject}"

    num, limits = 100, min(max(1, limits), 1000)
    url = f"https://www.google.com/search?q={query}&tbs=qdr:d{max(qdr, 1)}"

    params = {
        "hl": "zh-CN",
        "num": num,
    }

    starttime = time.time()
    collections = {}
    for start in range(0, limits, num):
        params["start"] = start
        content = re.sub(r"\\\\n", "", utils.http_get(url=url, params=params))
        content = re.sub(r"\?token\\\\u003d", "?token=", content, flags=re.I)
        regex = r'https?://(?:[a-zA-Z0-9_\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9_\u4e00-\u9fa5\-]+/?(?:<em(?:\s+)?class="qkunPe">/?)?api/v1/client/subscribe\?token(?:</em>)?=[a-zA-Z0-9]{16,32}'
        subscribes = re.findall(regex, content)
        for s in subscribes:
            s = re.sub(r'<em(?:\s+)?class="qkunPe">|</em>|\s+', "", s).replace("http://", "https://", 1)
            try:
                if exclude and re.search(exclude, s):
                    continue
                collections[s] = {"push_to": push_to, "origin": Origin.GOOGLE.name}
            except:
                continue

        # no more results
        if re.search(
            r'<p aria-level="3" role="heading".*?>\s*找不到和您查询的“\s*<span>\s*.*?/api/v1/client/subscribe\?token=.*?\s*</span>\s*”相符的内容或信息。\s*</p>',
            content,
            flags=re.I,
        ):
            break

        time.sleep(interval)

    cost = "{:.2f}s".format(time.time() - starttime)
    logger.info(f"[GoogleCrawl] finished crawl from Google, found {len(collections)} subscriptions, cost: {cost}")
    return collections


def crawl_yandex(
    within: int = 2,
    push_to: list = [],
    exclude: str = "",
    pages: int = 5,
    interval: int = 0,
    notinurl: list = [],
) -> dict:
    reject, query = "", urllib.parse.quote("/api/v1/client/subscribe?token=")
    if notinurl and type(notinurl) == list:
        items = list(set([re.escape(utils.trim(x).lower()) for x in notinurl]))
        reject = "|".join(items)

    url = f'https://yandex.com/search/?text="{query}"&lr=10599&cee=1'
    if within > 0:
        url = f"{url}&within={within}"

    starttime = time.time()

    headers = {
        "User-Agent": utils.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip",
    }

    # get total pages
    content = utils.http_get(url=url, headers=headers)
    if content:
        regex = r'<a class="VanillaReact Pager-Item Pager-Item_type_page" href=".*?" aria-label="Page \d+".*?>(\d+)</a>'
        groups = re.findall(regex, content, flags=re.I)
        if groups:
            pages = min(pages, max([int(x) for x in groups]))

    collections, pages = {}, max(1, pages)

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
            except:
                logger.error(f"[YandexCrawl] invalid regex pattern: {reject}")
                continue

            regex = r"https?://(?:[a-zA-Z0-9_\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9_\u4e00-\u9fa5\-]+/<b>api</b>/<b>v</b><b>1</b>/<b>client</b>/<b>subscribe</b>\?<b>token</b>=[a-zA-Z0-9]{16,32}"
            links = re.findall(regex, group, flags=re.I)
            for link in links:
                try:
                    link = re.sub(r"<b>|</b>", "", link).replace("http://", "https://")
                    if exclude and re.search(exclude, link):
                        continue
                    collections[link] = {
                        "push_to": push_to,
                        "origin": Origin.YANDEX.name,
                    }
                except:
                    continue

        time.sleep(interval)

    cost = "{:.2f}s".format(time.time() - starttime)
    logger.info(f"[YandexCrawl] finished crawl from Yandex, found {len(collections)} subscriptions, cost: {cost}")
    return collections


def crawl_github_page(page: int, cookie: str, push_to: list = [], exclude: str = "") -> dict:
    content = search_github_code(page=page, cookie=cookie)
    return extract_subscribes(content=content, push_to=push_to, exclude=exclude, source=Origin.GITHUB.name)


def search_github(page: int, cookie: str, searchtype: str, sortedby: str) -> str:
    if page <= 0 or utils.isblank(cookie):
        return ""

    searchtype = "Code" if utils.isblank(searchtype) else searchtype
    sortedby = "indexed" if utils.isblank(sortedby) else sortedby

    # search with regex for code
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


def paging(start: int, end: int, peer_page: int) -> list[int]:
    if start > end or peer_page <= 0:
        return []

    pages = []
    for i in range(start, end + 1, peer_page):
        pages.append(i // peer_page + 1)

    return pages


def search_github_issues(page: int, cookie: str) -> list[str]:
    content = search_github(page=page, cookie=cookie, searchtype="Issues", sortedby="created")
    if utils.isblank(content):
        return []

    try:
        regex = r'href="(/.*/.*/issues/\d+)">'
        groups = re.findall(regex, content, flags=re.I)
        links = list(set(groups))
        links = [f"https://github.com{x}" for x in links]
        return links
    except:
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
            if utils.isblank(link):
                continue
            links.add(link)

        return list(links)
    except:
        logger.error("[GithubIssuesCrawl] occur error when search issues from github")
        traceback.print_exc()
        return []


def search_github_code_byapi(token: str, peer_page: int = 50, page: int = 1, excludes: list = []) -> list[str]:
    """
    curl -Ls -o response.json -H "Authorization: Bearer <token>" https://api.github.com/search/code?q=%22%2Fapi%2Fv1%2Fclient%2Fsubscribe%3Ftoken%3D%22&sort=indexed&order=desc&per_page=30&page=1
    """
    if utils.isblank(token):
        return []

    peer_page, page = min(max(peer_page, 1), 100), max(1, page)
    url = f"https://api.github.com/search/code?q=%22%2Fapi%2Fv1%2Fclient%2Fsubscribe%3Ftoken%3D%22&sort=indexed&order=desc&per_page={peer_page}&page={page}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        # "X-GitHub-Api-Version": "2022-11-28"
    }
    content, links = utils.http_get(url=url, headers=headers), set()
    if utils.isblank(content):
        return []
    try:
        items = json.loads(content).get("items", [])
        excludes = list(set(excludes))
        for item in items:
            if not item or type(item) != dict:
                continue

            link = item.get("html_url", "")
            if utils.isblank(link):
                continue

            reponame = item.get("repository", {}).get("full_name", "") + "/"
            if not intercept(text=reponame, excludes=excludes):
                links.add(link)

        return list(links)
    except:
        return []


def search_github_code(page: int, cookie: str, excludes: list = []) -> list[str]:
    content = search_github(page=page, cookie=cookie, searchtype="Code", sortedby="indexed")
    if utils.isblank(content):
        return []

    try:
        regex = r'href="(/[^\s"]+/blob/(?:[^"]+)?)#L\d+"'
        groups = re.findall(regex, content, flags=re.I)
        uris, links = list(set(groups)) if groups else [], set()
        excludes = list(set(excludes))

        for uri in uris:
            if not intercept(text=uri, excludes=excludes):
                links.add(f"https://github.com{uri}")

        return list(links)
    except:
        return []


def intercept(text: str, excludes: list = []) -> bool:
    if not excludes:
        return False

    for regex in excludes:
        try:
            if re.search(regex, text, flags=re.I):
                return True
        except:
            logger.error(f"[GithubRepoIntercept] invalid regex pattern: {regex}")
    return False


def crawl_github(limits: int = 3, push_to: list = [], spams: list = [], exclude: str = "") -> dict:
    # user_session=${any}
    cookie = os.environ.get("GH_COOKIE", "").strip()
    token = os.environ.get("GH_TOKEN", "").strip()
    if utils.isblank(cookie) and utils.isblank(token):
        logger.error("[GithubCrawl] cannot start crawl from github because cookie and token is missing")
        return {}

    links, starttime = [], time.time()
    method = "search on the page" if utils.isblank(token) else "rest api"

    if utils.isblank(token):
        # 鉴于github搜索code不稳定，爬取两次
        pages = [x for x in range(1, limits + 1)] * 2
        params = [[x, cookie, spams] for x in pages]

        results = utils.multi_thread_run(func=search_github_code, tasks=params)
        items = list(set(itertools.chain.from_iterable(results)))

        links.extend(items)
        links.extend(search_github_issues(page=1, cookie=cookie))
    else:
        peer_page, count = 50, 10
        pages = paging(start=1, end=limits * count, peer_page=peer_page)
        params = [[token, peer_page, x, spams] for x in pages] * 2

        results = utils.multi_thread_run(func=search_github_code_byapi, tasks=params)
        items = list(set(itertools.chain.from_iterable(results)))

        links.extend(items)
        links.extend(search_github_issues_byapi(peer_page=5, page=1))

    if links:
        page_tasks = {}
        exclude = "" if not exclude else exclude.strip()

        for link in links:
            page_tasks[link] = {"push_to": push_to, "exclude": exclude}
        subscribes = crawl_pages(pages=page_tasks, silent=True, origin=Origin.GITHUB.name)
    else:
        subscribes = {}

    cost = "{:.2f}s".format(time.time() - starttime)
    logger.info(
        f"[GithubCrawl] finished crawl from Github through {method}, found {len(subscribes)} subscriptions need check, cost: {cost}"
    )

    return subscribes


def crawl_single_page(
    url: str,
    push_to: list = [],
    include: str = "",
    exclude: str = "",
    config: dict = {},
    headers: dict = None,
    origin: str = Origin.PAGE.name,
    nocache: bool = False,
) -> dict:
    if not url or not push_to:
        logger.error(f"[PageCrawl] cannot crawl from page: {url}")
        return {}

    content = utils.http_get(url=url, headers=headers)
    if content == "":
        return {}

    return extract_subscribes(
        content=content,
        push_to=push_to,
        include=include,
        exclude=exclude,
        config=config,
        source=origin,
        nocache=nocache,
    )


def crawl_pages(
    pages: dict,
    silent: bool = False,
    headers: dict = None,
    origin: str = Origin.PAGE.name,
) -> dict:
    if not pages:
        return {}

    params, starttime = [], time.time()
    for k, v in pages.items():
        if not isurl(url=k):
            continue

        push_to = v.get("push_to", [])
        include = v.get("include", "").strip()
        exclude = v.get("exclude", "").strip()
        config = v.get("config", {})
        nocache = v.get("nocache", False)

        final_headers = deepcopy(headers) if headers and isinstance(headers, dict) else utils.DEFAULT_HTTP_HEADERS
        specific_headers = v.get("headers", {})
        if specific_headers and isinstance(specific_headers, dict):
            final_headers.update(specific_headers)

        params.append([k, push_to, include, exclude, config, final_headers, origin, nocache])

    subscribes = multi_thread_crawl(func=crawl_single_page, params=params)
    if not silent:
        cost = "{:.2f}s".format(time.time() - starttime)
        logger.info(f"[PageCrawl] finished crawl from Page, found {len(subscribes)} subscriptions, cost: {cost}")

    return subscribes


def extract_twitter_cookies(retry: int = 2) -> str:
    if retry <= 0:
        return ""

    headers = None
    try:
        request = urllib.request.Request(url="https://twitter.com/", headers=utils.DEFAULT_HTTP_HEADERS)
        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
        headers = response.headers
    except urllib.error.HTTPError as e:
        if e.code != 302:
            return extract_twitter_cookies(retry=retry - 1)

        headers = e.headers
    except (urllib.error.URLError, TimeoutError):
        return extract_twitter_cookies(retry=retry - 1)

    if not headers or "set-cookie" not in headers:
        return ""

    regex = "(guest_id|guest_id_ads|guest_id_marketing|personalization_id)=(.+?);"
    content = ";".join(headers.get_all("set-cookie", ""))
    groups = re.findall(regex, content, flags=re.I)
    cookies = ";".join(["=".join(x) for x in groups]).strip()

    return cookies


def get_guest_token() -> str:
    cookies = extract_twitter_cookies(retry=3)
    if not cookies:
        logger.error(f"[TwitterCrawl] cannot extract Twitter cookies")
        return ""

    headers = {
        "User-Agent": utils.USER_AGENT,
        "Cookie": cookies,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    }
    content = utils.http_get(url="https://twitter.com/", headers=headers)
    if not content:
        return ""

    matcher = re.findall("gt=([0-9]{19})", content, flags=re.I)
    return matcher[0] if matcher else ""


def username_to_id(username: str, headers: dict) -> str:
    if utils.isblank(username):
        return ""

    if not headers or "X-Guest-Token" not in headers:
        guest_token = get_guest_token()
        if not guest_token:
            return ""

        headers = {
            "User-Agent": utils.USER_AGENT,
            "Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
            "X-Guest-Token": guest_token,
            "Content-Type": "application/json",
        }

    variables = {
        "screen_name": username.lower().strip(),
        "withSafetyModeUserFields": True,
    }
    features = {
        "blue_business_profile_image_shape_enabled": True,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
    }

    payload = urllib.parse.urlencode({"variables": json.dumps(variables), "features": json.dumps(features)})
    url = f"https://twitter.com/i/api/graphql/sLVLhk0bGj3MVFEKTdax1w/UserByScreenName?{payload}"
    try:
        content = utils.http_get(url=url, headers=headers)
        if not content:
            return ""

        data = json.loads(content).get("data", {}).get("user", {}).get("result", "")
        return data.get("rest_id", "")
    except:
        logger.error(f"[TwitterCrawl] cannot query uid by username=[{username}]")
        return ""


def crawl_twitter(tasks: dict) -> dict:
    if not tasks:
        return {}

    # extract X-Guest-Token
    guest_token, starttime = get_guest_token(), time.time()
    if not guest_token:
        logger.error(f"[TwitterCrawl] cannot extract X-Guest-Token from twitter")
        return {}

    headers = {
        "User-Agent": utils.USER_AGENT,
        "Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "X-Guest-Token": guest_token,
        "Content-Type": "application/json",
    }

    features = {
        "blue_business_profile_image_shape_enabled": True,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "tweetypie_unmention_optimization_enabled": True,
        "vibe_api_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "tweet_awards_web_tipping_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": False,
        "interactive_text_enabled": True,
        "responsive_web_text_conversations_enabled": False,
        "longform_notetweets_rich_text_read_enabled": True,
        "responsive_web_enhance_cards_enabled": False,
    }

    candidates, pages = {}, {}
    for k, v in tasks.items():
        if utils.isblank(k) or not v or type(v) != dict:
            continue
        candidates[k] = v

    if not candidates:
        return {}

    # username to uid
    params = [[k, headers] for k in candidates.keys()]
    uids = utils.multi_thread_run(func=username_to_id, tasks=params)

    for i in range(len(uids)):
        uid = uids[i]
        if not uid:
            continue

        config = candidates.get(params[i][0])
        count = config.pop("num", 10)
        variables = {
            "userId": uid,
            "count": min(max(count, 1), 100),
            "includePromotedContent": False,
            "withClientEventToken": False,
            "withBirdwatchNotes": False,
            "withVoice": True,
            "withV2Timeline": True,
        }

        payload = urllib.parse.urlencode({"variables": json.dumps(variables), "features": json.dumps(features)})
        url = f"https://twitter.com/i/api/graphql/P7qs2Sf7vu1LDKbzDW9FSA/UserMedia?{payload}"
        pages[url] = config

    subscribes = crawl_pages(pages=pages, silent=True, headers=headers, origin=Origin.TWITTER.name)
    cost = "{:.2f}s".format(time.time() - starttime)
    logger.info(f"[TwitterCrawl] finished crawl from Twitter, found {len(subscribes)} subscriptions, cost: {cost}")

    return subscribes


def extract_subscribes(
    content: str,
    push_to: list = [],
    include: str = "",
    exclude: str = "",
    limits: int = sys.maxsize,
    source: str = Origin.OWNED.name,
    config: dict = {},
    reversed: bool = False,
    nocache: bool = False,
) -> dict:
    if not content:
        return {}
    try:
        limits, collections, proxies = max(1, limits), {}, []
        sub_regex = r"https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+(?:(?:(?:/index.php)?/api/v1/client/subscribe\?token=[a-zA-Z0-9]{16,32})|(?:/link/[a-zA-Z0-9]+\?(?:sub|mu|clash)=\d))|https://jmssub\.net/members/getsub\.php\?service=\d+&id=[a-zA-Z0-9\-]{36}(?:\S+)?"
        extra_regex = r"https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+/sub\?(?:\S+)?target=\S+"
        protocal_regex = r"(?:vmess|trojan|ss|ssr|snell|hysteria2|vless|hysteria|tuic)://[a-zA-Z0-9:.?+=@%&#_\-/]{10,}"

        regex = f"{sub_regex}|{extra_regex}"

        if include:
            try:
                if not include.startswith("|"):
                    pattern = f"{regex}|{include}"
                else:
                    pattern = f"{regex}{include}"

                subscribes = re.findall(pattern, content, flags=re.I)
            except:
                logger.error(f"[ExtractError] maybe pattern 'include' exists some problems, include: {include}")
                subscribes = re.findall(regex, content)
        else:
            subscribes = re.findall(regex, content, flags=re.I)

        # 去重会打乱原本按日期排序的特性一致无法优先选择离当前时间较近的元素
        # subscribes = list(set(subscribes))

        if reversed:
            subscribes.reverse()

        for sub in subscribes:
            items = [sub]
            # subconverter url
            if "url=" in sub:
                qs, items = urllib.parse.urlparse(sub.replace("&amp;", "&")).query, []
                urls = urllib.parse.parse_qs(qs).get("url", [])
                if not urls:
                    continue

                for url in urls:
                    if not utils.isurl(url):
                        if allow_single_link():
                            proxies.extend([x for x in url.split("|") if re.match(protocal_regex, x, flags=re.I)])
                        continue

                    items.extend([x for x in url.split("|") if not re.match(extra_regex, x, flags=re.I)])

            for s in items:
                s = re.sub(r"\\/|\/", "/", s, flags=re.I)
                try:
                    if include and not re.match(
                        r"https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+.*",
                        s,
                        flags=re.I,
                    ):
                        continue

                    if exclude and re.search(exclude, s):
                        continue
                except:
                    logger.error(
                        f"[ExtractError] maybe pattern 'include' or 'exclude' exists some problems, include: {include}\texclude: {exclude}"
                    )

                # 强制使用https协议
                # s = s.replace("http://", "https://", 1).strip()
                params = {"push_to": push_to, "origin": source, "nocache": nocache}
                if config:
                    params.update(config)
                collections[s] = params

            if len(collections) >= limits:
                break

        if allow_single_link():
            try:
                groups = re.findall(protocal_regex, content, flags=re.I)
                if groups:
                    proxies.extend([x.lower().strip() for x in groups if x])
                    params = {
                        "push_to": push_to,
                        "origin": source,
                        "proxies": list(set(proxies)),
                    }
                    if config:
                        params.update(config)
                    collections[SINGLE_LINK_FLAG] = params
            except:
                logger.error(f"[ExtractError] failed to extract single proxy")

        return collections
    except:
        logger.error("[ExtractError] extract subscribe error")
        return {}


def validate(
    url: str,
    params: dict,
    mode: int,
    connectable: bool,
    exclude: str = "",
    threshold: int = 1,
) -> ValidateResult:
    if (
        not params
        or not params.get("push_to", None)
        or not params.get("origin", "")
        or (exclude and re.search(exclude, url))
    ):
        return ValidateResult()

    result = ValidateResult()
    if url.startswith(SINGLE_LINK_FLAG):
        proxies = params.get("proxies", [])
        if proxies and type(proxies) == list:
            result.proxies = set(proxies)

        return result

    threshold = max(threshold, 1)
    defeat = params.get("defeat", 0) + 1
    discovered = params.get("discovered", False)

    reachable, expired = check_status(url=url, retry=2, remain=5, spare_time=12, tolerance=72, connectable=connectable)
    if reachable:
        item = {"name": naming_task(url), "sub": url, "debut": True}
        item.update(params)
        result.available = item

        # reset defeat to 0
        defeat = 0
        discovered = True

    if not params.pop("saved", False):
        if reachable or (discovered and defeat <= threshold and not expired):
            # don't storage temporary link shared by someone
            pardon = params.pop("pardon", False)
            if not pardon and not workflow.standard_sub(url=url) and mode != 1:
                return result

            remark(source=params, defeat=defeat, discovered=True)
            result.potential = {url: params}
        elif not connectable and not expired:
            result.unknown = url

    return result


def remark(source: dict, defeat: int = 0, discovered: bool = True) -> None:
    if not source or type(source) != dict or type(defeat) != int or defeat < 0 or type(discovered) != bool:
        return

    source["defeat"] = defeat
    source["discovered"] = discovered
    if utils.isblank(source.get("origin", "")):
        source["origin"] = Origin.TEMPORARY.name


def check_status(
    url: str,
    retry: int = 2,
    remain: float = 0,
    spare_time: float = 0,
    tolerance: float = 0,
    connectable: bool = True,
) -> tuple[bool, bool]:
    """
    url: subscription link
    retry: number of retries
    remain: minimum remaining traffic flow
    spare_time: minimum remaining time
    tolerance: waiting time after expiration
    """
    if not url or retry <= 0:
        return False, connectable

    try:
        headers = {"User-Agent": "clash.meta"}
        request = urllib.request.Request(url=url, headers=headers)
        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
        if response.getcode() != 200:
            return False, connectable

        # in order to avoid the request to the speed test site causing constant data downloads, limit the maximum read to 15MB
        content = str(response.read(15 * 1024 * 2014), encoding="utf8")

        # response text is too short, ignore
        if len(content) < 32:
            return False, False

        # 订阅流量信息
        subscription = response.getheader("subscription-userinfo")

        if utils.isb64encode(content):
            # parse and detect whether the subscription has expired
            return is_expired(header=subscription, remain=remain, spare_time=spare_time, tolerance=tolerance)

        try:
            proxies = yaml.load(content, Loader=yaml.SafeLoader).get("proxies", [])
        except ConstructorError:
            yaml.add_multi_constructor("str", lambda loader, suffix, node: str(node.value), Loader=yaml.SafeLoader)
            proxies = yaml.load(content, Loader=yaml.FullLoader).get("proxies", [])
        except:
            if all(airport.AirPort.check_protocol(x) for x in content.split("\n") if x):
                return True, False

            # TODO: 如果配置文件为 singbox、quanx、loon、surge等，需要解析出代理节点信息，并判断是否过期
            proxies = []

        if proxies is None or len(proxies) == 0:
            return False, True

        # 根据订阅信息判断是否有效
        return is_expired(header=subscription, remain=remain, spare_time=spare_time, tolerance=tolerance)
    except urllib.error.HTTPError as e:
        try:
            message = str(e.read(), encoding="utf8")
        except:
            message = ""

        expired = e.code == 404 or "token is error" in message
        if not expired and e.code in [403, 503]:
            return check_status(
                url=url,
                retry=retry - 1,
                remain=remain,
                spare_time=spare_time,
                tolerance=tolerance,
                connectable=connectable,
            )

        return False, expired
    except Exception as e:
        return check_status(
            url=url,
            retry=retry - 1,
            remain=remain,
            spare_time=spare_time,
            tolerance=tolerance,
            connectable=connectable,
        )


def is_expired(header: str, remain: float = 0, spare_time: float = 0, tolerance: float = 0) -> tuple[bool, bool]:
    if utils.isblank(header):
        return True, False

    remain, spare_time, tolerance = (
        max(0, remain),
        max(spare_time, 0),
        max(tolerance, 0),
    )
    try:
        infos = header.split(";")
        upload, download, total, expire = 0, 0, 0, None
        for info in infos:
            words = info.split("=", maxsplit=1)
            if len(words) <= 1:
                continue

            if "upload" == words[0].strip():
                upload = eval(words[1])
            elif "download" == words[0].strip():
                download = eval(words[1])
            elif "total" == words[0].strip():
                total = eval(words[1])
            elif "expire" == words[0].strip():
                expire = None if utils.isblank(words[1]) else eval(words[1])

        # 剩余流量大于 ${remain} GB 并且未过期则返回 True，否则返回 False
        flag = total - (upload + download) > remain * pow(1024, 3) and (
            expire is None or expire - time.time() > spare_time * 3600
        )
        expired = False if flag else (expire is not None and (expire + tolerance * 3600) <= time.time())
        return flag, expired
    except:
        return True, False


def is_available(url: str, retry: int = 2, remain: float = 0, spare_time: float = 0) -> bool:
    available, _ = check_status(url=url, retry=retry, remain=remain, spare_time=spare_time)
    return available


def naming_task(url) -> str:
    prefix = utils.extract_domain(url=url).replace(".", "") + SEPARATOR
    return prefix + "".join(random.sample(string.digits + string.ascii_lowercase, random.randint(3, 5)))


def get_telegram_pages(channel: str) -> int:
    if not channel or channel.strip() == "":
        return 0

    url = f"https://t.me/s/{channel}"
    content = utils.http_get(url=url)
    before = 0
    try:
        regex = rf'<link\s+rel="canonical"\s+href="/s/{channel}\?before=(\d+)">'
        groups = re.findall(regex, content)
        before = int(groups[0]) if groups else before
    except:
        logger.error(f"[CrawlError] cannot count page num, chanel: {channel}")

    return before


def extract_airport_site(url: str) -> list[str]:
    if not url:
        return []

    logger.info(f"[AirPortCrawl] start collect airport, url: {url}")

    content = utils.http_get(url=url)
    if not content:
        logger.error(f"[CrawlError] cannot any content from url: {url}")
        return []
    try:
        regex = r'href="(https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+/?)"\s+target="_blank"\s+rel="noopener">'
        groups = re.findall(regex, content)
        return list(set(groups)) if groups else []
    except:
        return []


def collect_airport(
    channel: str,
    page_num: int,
    num_thread: int = 64,
    rigid: bool = True,
    display: bool = True,
    filepath: str = "",
    delimiter: str = "",
    chuck: bool = False,
) -> dict:
    def crawl_channel(channel: str, page_num: int, fun: typing.Callable) -> list[str]:
        """crawl from telegram channel"""
        if not channel or not fun or not isinstance(fun, typing.Callable):
            return []

        page_num = max(page_num, 1)
        url = f"https://t.me/s/{channel}"
        if page_num == 1:
            return list(fun(url))
        else:
            count = get_telegram_pages(channel=channel)
            if count == 0:
                return []

            pages = range(count, -1, -20)
            page_num = min(page_num, len(pages))
            logger.info(f"[TelegramCrawl] starting crawl from telegram, channel: {channel}, pages: {page_num}")

            urls = [f"{url}?before={x}" for x in pages[:page_num]]
            results = utils.multi_thread_run(func=fun, tasks=urls)

            return list(itertools.chain.from_iterable(results))

    def crawl_ccbh() -> dict:
        url = "https://ccbaohe.com/jcjd.html"
        content = utils.http_get(url=url)
        try:
            groups = re.split(r"【[^【]*】", content, flags=re.M)
            if not groups:
                logger.warning(f"[AirPortCollector] cannot found any domains from [{url}]")
                return {}

            candidates, result = {}, {}
            for group in groups:
                if not group:
                    continue

                texts = group.split("<br/><br/>")
                for text in texts:
                    address_regex = r'注册地址：<a href="(https?://[^\s]+)"'
                    words = re.findall(address_regex, text, flags=re.M)
                    address = words[0] if words else ""

                    if not address:
                        continue

                    coupon_regex = r"(?:白嫖|优惠)码[:\s：]+(?:<span.*?>)?([^\s\r\n<）]+)"
                    words = re.findall(coupon_regex, text, flags=re.M)
                    coupon = words[0] if words else ""

                    candidates[address] = coupon

            urls = list(candidates.keys())
            latest = utils.multi_thread_run(func=get_redirect_url, tasks=urls, num_threads=num_thread)

            for i, x in enumerate(urls):
                domain = utils.extract_domain(url=latest[i], include_protocal=True)
                if not domain:
                    continue

                coupon = candidates.get(x, "")
                result[domain] = coupon
        except:
            logger.error(f"[AirPortCollector] occur error when crawl from [{url}], message: \n{traceback.format_exc()}")

        logger.info(f"[AirPortCollector] finished crawl from [{url}], found {len(result)} domains")
        return result

    def crawl_maomeng() -> dict:
        return run_crawl(
            url="https://maomeng.xyz/2021/06/11/ji-chang-tui-jian-chang-qi-geng-xin",
            separator=r'<h3 id="[^\r\n]+"><a href="#[^\r\n]+"',
            address_regex=r"<p>官网：<a[^\r\n]+href=\"(https?://[^\s]+)\">.*</a></p>",
            coupon_regex=r"<p>(?:优惠|白嫖)码：<code>([^<]+)</code></p>",
        )

    def crawl_askahh() -> dict:
        return run_crawl(
            url="https://www.askahh.com/archives/101",
            separator=r"&lt;h2&gt;[^\r\n]+&lt;/h2&gt;",
            address_regex=r"&lt;a class=&quot;no-external-link&quot; href=&quot;(https?://[^\s]+)&quot; target=&quot;_blank&quot;&gt;",
            coupon_regex=r"使用优惠码(?:&lt;strong&gt;)?([A-Za-z0-9\u4e00-\u9fa5_\-%*:.@&#]+)(?:&lt;/strong&gt;(?:[\r\n\s]+)?)?免费购买",
        )

    def crawl_ygpy() -> dict:
        def get_links(url: str, prefix: str) -> list[str]:
            content = utils.http_get(url=url)

            groups = re.findall(r'href="(/vpn/\d{4}/\d{2}.html)"', content, flags=re.I)
            if not groups:
                logger.warning(f"[AirPortCollector] cannot fetch article from url: {url}")
                return []

            prefix = utils.trim(prefix)
            return list(set([urllib.parse.urljoin(prefix, x) for x in groups if x]))

        base = "https://ygpy.net"
        links = get_links(url=base, prefix=base)
        if not links:
            logger.warning(f"[AirPortCollector] cannot get article from url: {base}")
            return {}

        articles = get_links(url=links[0], prefix=base)
        if not articles:
            logger.warning(f"[AirPortCollector] cannot get articles from url: {links[0]}")
            return {}

        separator = r'<h2 id="\d+" tabindex="-1">'
        address_regex = r'<a href="(https?://[^\s]+)" target="_blank" rel="noreferrer nofollow">前往注册</a>'
        coupon_regex = r"使用优惠码(?:\s+)?(?:<code>)?([^\r\n\s]+)(?:</code>(?:[\r\n\s]+)?)?0(?:\s+)?元购买"

        tasks = [[x, separator, address_regex, coupon_regex] for x in sorted(articles)]
        items = utils.multi_thread_run(func=run_crawl, tasks=tasks)

        result = dict()
        for item in items:
            if item and isinstance(item, dict):
                result.update(item)

        return result

    def crawl_jctj(convert: bool = False) -> dict:
        url = "https://raw.githubusercontent.com/hwanz/SSR-V2ray-Trojan-vpn/main/README.md"
        content = utils.http_get(url=url)
        groups = re.findall(r"\[.*\]\((https?:\/\/[^\s\r\n]+)\)[^\r\n]+\d+G.*", content, flags=re.I)
        if not groups:
            return {}

        try:
            tasks = [utils.trim(x).lower() for x in groups if x]
            if convert:
                links = utils.multi_thread_run(func=get_redirect_url, tasks=tasks, num_threads=num_thread)
            else:
                links = tasks

            result = {utils.extract_domain(url=x, include_protocal=True): "" for x in links if x}
            logger.info(f"[AirPortCollector] finished crawl from [{url}], found {len(result)} domains")

            return result
        except:
            logger.error(f"[AirPortCollector] occur error when crawl from [{url}], message: \n{traceback.format_exc()}")
            return {}

    def get_redirect_url(url: str, retry: int = 3) -> str:
        if not url or retry <= 0:
            return ""

        headers = {
            "User-Agent": utils.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        try:
            request = urllib.request.Request(url=url, headers=headers, method="GET")
            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)

            return response.geturl()
        except:
            time.sleep(random.randint(1, 3))
            return get_redirect_url(url=url, retry=retry - 1)

    def run_crawl(url: str, separator: str, address_regex: str, coupon_regex: str) -> dict:
        url = utils.trim(url)
        content = utils.http_get(url=url)
        if not content:
            return {}

        result = dict()
        try:
            groups = re.split(utils.trim(separator), content, flags=re.M)
            if not groups:
                logger.warning(f"[AirPortCollector] cannot found any domains from [{url}]")
                return {}

            for group in groups:
                words = re.findall(utils.trim(address_regex), group, flags=re.M)
                address = words[0] if words else ""
                if not address:
                    continue

                words = re.findall(utils.trim(coupon_regex), group, flags=re.M)
                coupon = words[0] if words else ""

                domain = utils.extract_domain(url=address, include_protocal=True)
                result[domain] = coupon
        except:
            logger.error(f"[AirPortCollector] occur error when crawl from [{url}], message: \n{traceback.format_exc()}")

        logger.info(f"[AirPortCollector] finished crawl from [{url}], found {len(result)} domains")
        return result

    def extract_backend_url(domain: str, retry: int = 2) -> str:
        # TODO: exploring a more generalized approach to backend addresses
        def request_once(suffix: str) -> tuple[bool, str]:
            count, suffix = 0, utils.trim(suffix)
            url = urllib.parse.urljoin(domain, suffix)

            while count < retry:
                count += 1

                try:
                    request = urllib.request.Request(url=url, headers=utils.DEFAULT_HTTP_HEADERS, method="GET")
                    response = urllib.request.urlopen(request, timeout=6, context=utils.CTX)

                    word = "" if not suffix else (suffix if suffix.startswith("/") else "/" + suffix)
                    if word and not utils.trim(response.geturl()).endswith(word):
                        return True, ""

                    content = response.read()
                    try:
                        content = str(content, encoding="utf8")
                    except:
                        content = gzip.decompress(content).decode("utf8")

                    return False, content
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        return False, ""
                except urllib.error.URLError as e:
                    if isinstance(e.reason, (socket.gaierror, ssl.SSLError, socket.timeout)):
                        return True, ""
                except Exception as e:
                    pass

            return False, ""

        def attempt_env() -> str:
            status, content = request_once(suffix="/env.js")
            if status:
                return terminated

            if not content:
                return ""

            if groups := re.findall(r"\bhost\b:(?:\s+)?[\"\'](https?://[^\s\r\t]+)[\"\']", content, flags=re.I):
                return utils.trim(groups[0])

            groups = re.findall(r"window.routerBase(?:\s+)?=(?:\s+)?['\"](https?://.*)['\"]", content, flags=re.I)
            return groups[0].rstrip("/") if groups and groups[0] else ""

        def attempt_zero() -> str:
            status, content = request_once(suffix="/config.json")
            if status:
                return terminated

            if not content:
                return ""

            try:
                data = json.loads(content)
                # for https://github.com/amyouran/v2board-Zero-Theme
                link = utils.trim(data.get("api_base", ""))
                if not link:
                    # for https://github.com/DyAxy/V2B-Theme-Nest
                    link = utils.trim(data.get("apiUrl", ""))

                return utils.extract_domain(url=link, include_protocal=True)
            except:
                return ""

        def attempt_buddy() -> str:
            # for https://github.com/vlesstop/v2board-theme-buddy
            status, content = request_once(suffix="/config.js")
            if status:
                return terminated

            group = re.findall(r"\bhost\b:(?:\s+)?[\"\'](https?://[^\s\r\t]+)[\"\']", content, flags=re.I)
            return "" if not group else utils.trim(group[0])

        def attempt_aurora() -> str:
            # for https://github.com/krsunm/Aurora
            status, content = request_once(suffix="")
            if status:
                return terminated

            group = re.findall(r"\bserverUrl\b:(?:\s+)?[\"\'](https?://[^\s\r\t]+)[\"\']", content, flags=re.I)
            return "" if not group else utils.trim(group[0])

        terminated, retry = "terminated", max(retry, 1)
        for func in [attempt_env, attempt_zero, attempt_buddy, attempt_aurora]:
            backend = func()
            if terminated == backend:
                return ""
            if backend:
                return backend

        return domain

    domains = crawl_channel(channel=channel, page_num=page_num, fun=extract_airport_site)
    candidates = {} if not domains else {utils.extract_domain(x, True): "" for x in domains}

    materials = dict()
    jctj = crawl_jctj(convert=False)
    if jctj:
        materials.update(jctj)

    ccbh = crawl_ccbh()
    if ccbh:
        materials.update(ccbh)

    maomeng = crawl_maomeng()
    if maomeng:
        materials.update(maomeng)

    askahh = crawl_askahh()
    if askahh:
        materials.update(askahh)

    ygpy = crawl_ygpy()
    if ygpy:
        materials.update(ygpy)

    # save to file cause they often contain coupons and require common emails to use
    save_candidates(candidates=materials, filepath=filepath, delimiter=delimiter)

    # merge
    candidates.update(materials)
    domains = list(candidates.keys())

    # extract real routing base url
    logger.info(f"[AirPortCollector] fetched {len(domains)} airport, start extracting real routing addresses")
    sites = utils.multi_thread_run(
        func=extract_backend_url,
        tasks=domains,
        num_threads=num_thread,
        show_progress=display,
    )

    tasks = [[site, rigid, chuck] for site in sites if site]
    records = {sites[i]: candidates.get(domains[i], "") for i in range(len(sites)) if sites[i]}

    # check website availability
    logger.info(f"[AirPortCollector] extract real base url finished, start to check it now")
    result = utils.multi_thread_run(func=validate_domain, tasks=tasks, num_threads=num_thread, show_progress=display)

    availables = dict()
    for i in range(len(tasks)):
        if not result[i][0]:
            continue

        site = tasks[i][0]
        coupon = records.get(site, "")
        availables[site] = {"coupon": coupon, "api_prefix": result[i][1]}

    logger.info(f"[AirPortCollector] finished collect airport, availables: {len(availables)}")
    return availables


def save_candidates(candidates: dict, filepath: str, delimiter: str) -> None:
    if not candidates or not isinstance(candidates, dict):
        return

    filepath = utils.trim(filepath)
    if not filepath:
        return

    delimiter = utils.trim(delimiter) or "@#@#"

    lines = []
    for k, v in candidates.items():
        text = k
        if v and isinstance(v, str):
            text += f"\t{delimiter}\t{v}"
        elif v and isinstance(v, dict):
            coupon = utils.trim(v.get("coupon", ""))
            invite_code = utils.trim(v.get("invite_code", ""))
            api_prefix = utils.trim(v.get("api_prefix", ""))

            text = f"{text}\t{delimiter}\t{coupon}\t{delimiter}\t{invite_code}\t{delimiter}\t{api_prefix}"
        lines.append(text)

    utils.write_file(filename=filepath, lines=lines)


def validate_domain(url: str, rigid: bool = True, chuck: bool = False) -> tuple[bool, str]:
    try:
        if not url:
            return False, ""

        rr = airport.AirPort.get_register_require(domain=url)
        flag = rr.invite or (chuck and rr.recaptcha) or (rigid and rr.whitelist and rr.verify)
        return not flag, rr.api_prefix
    except:
        return False, ""


def batch_call(tasks: dict) -> list[dict]:
    if not tasks:
        return []

    try:
        num_thread = max(min(len(tasks), 50), 1)
        with multiprocessing.Manager() as manager:
            availables = manager.list()
            processes = []
            semaphore = multiprocessing.Semaphore(num_thread)
            time.sleep(random.randint(1, 3))
            for k, v in tasks.items():
                semaphore.acquire()
                p = multiprocessing.Process(target=call, args=(k, v, availables, semaphore))
                p.start()
                processes.append(p)
            for p in processes:
                p.join()

            return list(availables)
    except:
        traceback.print_exc()
        return []


def call(script: str, params: dict, availables: ListProxy, semaphore: Semaphore) -> None:
    try:
        if not script:
            return

        subscribes = execute_script(script=script, params=params)
        if subscribes and type(subscribes) == list:
            availables.extend(subscribes)
    finally:
        if semaphore is not None and isinstance(semaphore, Semaphore):
            semaphore.release()


def execute_script(script: str, params: dict = {}) -> list[dict]:
    try:
        # format: a.b.c#function or a-b.c#_function or a#function and so on
        regex = r"^([a-zA-Z0-9_]+|([0-9a-zA-Z_]+([a-zA-Z0-9_\-]+)?\.)+)[a-zA-Z0-9_\-]+#[a-zA-Z_]+[0-9a-zA-Z_]+$"
        if not re.match(regex, script):
            logger.info(f"[ScriptError] script execute error because script: {script} is invalidate")
            return []

        path, func_name = script.split("#", maxsplit=1)
        path = f"scripts.{path}"
        module = importlib.import_module(path)
        if not hasattr(module, func_name):
            logger.error(f"script: {path} not exists function {func_name}")
            return []

        func = getattr(module, func_name)

        starttime = time.time()
        logger.info(f"[ScriptInfo] start execute script: scripts.{script}")

        subscribes = func(params)
        if type(subscribes) != list:
            logger.error(f"[ScriptError] return value error, need a list, but got a {type(subscribes)}")
            return []

        endtime = time.time()
        logger.info(
            "[ScriptInfo] finished execute script: scripts.{}, cost: {:.2f}s".format(script, endtime - starttime)
        )

        subscribes = [s for s in subscribes if type(s) == dict and s.get("push_to", [])]
        return subscribes
    except:
        logger.error(f"[ScriptError] occur error run script: {script}, message: \n{traceback.format_exc()}")
        return []
