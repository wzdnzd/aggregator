# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import datetime
import itertools
import json
import multiprocessing
import os
import random
import re
import string
import sys
import time
import typing
from datetime import datetime
from multiprocessing.managers import ListProxy
from multiprocessing.synchronize import Semaphore

import utils
from airport import AirPort
from logger import logger
from origin import Origin

SEPARATOR = "-"


def multi_thread_crawl(fun: typing.Callable, params: list) -> dict:
    try:
        from collections.abc import Iterable
    except ImportError:
        from collections import Iterable

    if not fun or not params:
        return {}

    cpu_count = multiprocessing.cpu_count()
    num = len(params) if len(params) <= cpu_count else cpu_count

    pool = multiprocessing.Pool(num)
    if isinstance(params, Iterable):
        results = pool.starmap(fun, params)
    else:
        results = pool.map(fun, params)
    pool.close()

    tasks = {}
    for r in results:
        for k, v in r.items():
            item = tasks.get(k, {})
            item["origin"] = v.get("origin", item.get("origin", ""))
            pts = item.get("push_to", [])
            pts.extend(v.get("push_to", []))
            item["push_to"] = list(set(pts))
            tasks[k] = item

    return tasks


def batch_crawl(conf: dict, thread: int = 50) -> list:
    if not conf:
        return []

    try:
        tasks = {}
        google_spider = conf.get("google", [])
        if google_spider:
            tasks.update(crawl_google(qdr=7, push_to=google_spider))

        github_spider = conf.get("github", {})
        if github_spider and github_spider.get("push_to", []):
            push_to = github_spider.get("push_to")
            pages = github_spider.get("pages", 1)
            exclude = github_spider.get("exclude", "")
            tasks.update(crawl_github(limits=pages, push_to=push_to, exclude=exclude))

        telegram_spider = conf.get("telegram", {})
        if telegram_spider and telegram_spider.get("users", {}):
            users = telegram_spider.get("users")
            period = max(telegram_spider.get("period", 7), 7)
            tasks.update(crawl_telegram(users=users, period=period))

        repositories = conf.get("repositories", {})
        if repositories:
            tasks.update(crawl_github_repo(repos=repositories))

        pages = conf.get("pages", {})
        if pages:
            tasks.update(crawl_pages(pages=pages))

        if not tasks:
            logger.error("cannot found any subscribe url from crawler")
            return []

        with multiprocessing.Manager() as manager:
            availables = manager.list()
            processes = []
            semaphore = multiprocessing.Semaphore(max(thread, 1))
            time.sleep(random.randint(1, 3))
            for k, v in tasks.items():
                semaphore.acquire()
                p = multiprocessing.Process(
                    target=validate_available, args=(k, v, availables, semaphore)
                )
                p.start()
                processes.append(p)
            for p in processes:
                p.join()

            time.sleep(random.randint(1, 3))
            return list(availables)
    except:
        logger.error("crawl from web error")
        return []


def crawl_single_telegram(
    userid: str,
    period: int,
    push_to: list = [],
    include: str = "",
    exclude: str = "",
    limits: int = 20,
) -> dict:
    if not userid:
        return {}

    now = time.time() - 3600 * 8
    crawl_time = datetime.fromtimestamp(now).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"https://telemetr.io/post-list-ajax/{userid}/with-date-panel?period={period}&date={crawl_time}"

    content = utils.http_get(url=url)
    return extract_subscribes(
        content=content,
        push_to=push_to,
        include=include,
        limits=limits,
        source=Origin.TELEGRAM.name,
        exclude=exclude,
    )


def crawl_telegram(users: dict, period: int, limits: int = 20) -> dict:
    if not users:
        return {}

    period = max(period, 7)
    limits = max(1, limits)
    params = []
    for k, v in users.items():
        include = v.get("include", "")
        exclude = v.get("exclude", "").strip()
        pts = v.get("push_to", [])
        params.append([k, period, pts, include, exclude, limits])

    starttime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[TelegramCrawl] start crawl from Telegram, time: {starttime}")
    subscribes = multi_thread_crawl(fun=crawl_single_telegram, params=params)
    endtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(
        f"[TelegramCrawl] finished crawl from Telegram, time: {endtime}, subscribes: {list(subscribes.keys())}"
    )
    return subscribes


def crawl_single_repo(
    username: str, repo: str, push_to: list = [], limits: int = 5, exclude: str = ""
) -> dict:
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
        logger.error(f"crawl from github error, username: {username}\trepo: {repo}")
        return {}


def crawl_github_repo(repos: dict):
    if not repos:
        return {}
    params = []

    starttime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[RepoCrawl] start crawl from Repositorie, time: {starttime}")
    for _, v in repos.items():
        username = v.get("username", "").strip()
        repo_name = v.get("repo_name", "").strip()
        push_to = v.get("push_to", [])
        limits = max(v.get("commits", 2), 1)
        exclude = v.get("exclude", "").strip()

        if not username or not repo_name or not push_to:
            continue
        params.append([username, repo_name, push_to, limits, exclude])

    subscribes = multi_thread_crawl(fun=crawl_single_repo, params=params)
    endtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(
        f"[RepoCrawl] finished crawl from Repositorie, time: {endtime}, subscribes: {list(subscribes.keys())}"
    )
    return subscribes


def crawl_google(
    qdr: int = 10, push_to: list = [], limits: int = 100, interval: int = 0
) -> dict:
    url = f"https://www.google.com/search?tbs=qdr:d{max(qdr, 1)}"
    num, limits = 100, max(1, limits)
    params = {
        "q": '"/api/v1/client/subscribe?token="',
        "hl": "zh-CN",
        "num": num,
    }

    starttime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[GoogleCrawl] start crawl from Google, time: {starttime}")
    collections = {}
    for start in range(0, limits, num):
        params["start"] = start
        content = utils.http_get(url=url, params=params)
        regex = 'https?://(?:[a-zA-Z0-9_\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9_\u4e00-\u9fa5\-]+/?(?:<em(?:\s+)?class="qkunPe">/?)?api/v1/client/subscribe\?token(?:</em>)?=[a-zA-Z0-9]{16,32}'
        subscribes = re.findall(regex, content)
        for s in subscribes:
            s = re.sub('<em(?:\s+)?class="qkunPe">|</em>|\s+', "", s).replace(
                "http://", "https://", 1
            )
            s += "&flag=v2ray"
            collections[s] = {"push_to": push_to, "origin": Origin.GOOGLE.name}

        time.sleep(interval)

    endtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(
        f"[GoogleCrawl] finished crawl from Google, time: {endtime}, subscribes: {list(collections.keys())}"
    )
    return collections


def crawl_github_page(
    page: int, cookie: str, push_to: list = [], exclude: str = ""
) -> dict:
    if page <= 0 or not cookie:
        return {}

    url = f"https://github.com/search?o=desc&p={page}&q=%22%2Fapi%2Fv1%2Fclient%2Fsubscribe%3Ftoken%3D%22&s=indexed&type=Code"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Referer": "https://github.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.114 Safari/537.36 Edg/103.0.1264.62",
        "Cookie": f"user_session={cookie}",
    }
    content = utils.http_get(url=url, headers=headers)
    return extract_subscribes(
        content=content, push_to=push_to, exclude=exclude, source=Origin.GITHUB.name
    )


def crawl_github(limits: int = 3, push_to: list = [], exclude: str = "") -> dict:
    cookie = os.environ.get("GH_COOKIE", "").strip()
    if not cookie:
        logger.error(
            "[GithubCrawl] cannot start crawl from github because cookie is missing"
        )
        return {}

    # 鉴于github搜索code不稳定，爬取两次
    pages = range(1, limits + 1) * 2
    exclude = "" if not exclude else exclude.strip()
    params = [[x, cookie, push_to, exclude] for x in pages]
    starttime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[GithubCrawl] start crawl from Github, time: {starttime}")
    subscribes = multi_thread_crawl(fun=crawl_github_page, params=params)
    endtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(
        f"[GithubCrawl] finished crawl from Github, time: {endtime}, subscribes: {list(subscribes.keys())}"
    )

    return subscribes


def extract_subscribes(
    content: str,
    push_to: list = [],
    include: str = "",
    exclude: str = "",
    limits: int = sys.maxsize,
    source: str = Origin.OWNED.name,
) -> dict:
    if not content:
        return {}
    try:
        limits, collections = max(1, limits), {}
        regex = "https?://(?:[a-zA-Z0-9_\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9_\u4e00-\u9fa5\-]+(?:(?:(?:/index.php)?/api/v1/client/subscribe\?token=[a-zA-Z0-9]{16,32})|(?:/link/[a-zA-Z0-9]+\?(?:sub|mu)=\d))"

        if include:
            try:
                if not include.startswith("|"):
                    pattern = f"{regex}|{include}"
                else:
                    pattern = f"{regex}{include}"

                subscribes = re.findall(pattern, content)
            except:
                logger.error(
                    f"[ExtractError] maybe pattern 'include' exists some problems, include: {include}"
                )
                subscribes = re.findall(regex, content)
        else:
            subscribes = re.findall(regex, content)

        for s in subscribes:
            try:
                if include and not re.match(
                    "https?://(?:[a-zA-Z0-9_\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9_\u4e00-\u9fa5\-]+.*",
                    s,
                ):
                    continue

                if exclude and re.search(exclude, s):
                    continue
            except:
                logger.error(
                    f"[ExtractError] maybe pattern 'include' or 'exclude' exists some problems, include: {include}\texclude: {exclude}"
                )

            # 强制使用https协议
            s = s.replace("http://", "https://", 1).strip()

            if "token=" in s:
                s += "&flag=v2ray"
            collections[s] = {"push_to": push_to, "origin": source}
            if len(collections) >= limits:
                break

        return collections
    except:
        logger.error("extract subscribe error")
        return {}


def validate_available(
    url: str, params: dict, availables: ListProxy, semaphore: Semaphore
) -> None:
    try:
        if (
            not params
            or not params.get("push_to", None)
            or not params.get("origin", "")
        ):
            return

        if utils.http_get(url=url, retry=2) != "":
            item = {
                "name": naming_task(url),
                "sub": url,
                "push_to": params.get("push_to"),
                "origin": params.get("origin"),
                "debut": True,
            }

            availables.append(item)
    finally:
        if semaphore is not None and isinstance(semaphore, Semaphore):
            semaphore.release()


def naming_task(url):
    prefix = utils.extract_domain(url=url).replace(".", "") + SEPARATOR
    return prefix + "".join(
        random.sample(string.digits + string.ascii_lowercase, random.randint(3, 5))
    )


def collect_airport_page(url: str) -> list:
    if not url:
        return []

    logger.info(f"[AirPortCrawl] start collect airport, url: {url}")

    content = utils.http_get(url=url)
    if not content:
        logger.error(f"[CrawlError] cannot any content from url: {url}")
        return []

    try:
        regex = '官网:.*"link\s+to\s+url"\>(https?://(?:[a-zA-Z0-9_\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9_\u4e00-\u9fa5\-]+)\</a\>'
        groups = re.findall(regex, content)
        return list(set(groups)) if groups else []
    except:
        return []


def collect_airport(
    channel_id: int, group_name: str, page_num: int, thread_num: int = 50
) -> list:
    def get_pages(channel: str) -> int:
        if not channel or channel.strip() == "":
            return 0

        url = f"https://telemetr.io/en/channels/{channel}/posts"
        content = utils.http_get(url=url)
        before = 0
        try:
            regex = f"https://telemetr.io/en/channels/{channel}/posts\?before=(\d+)"
            groups = re.findall(regex, content)
            before = int(groups[0]) + 100 if groups else before
        except:
            logger.error(f"[CrawlError] cannot count page num, chanel: {channel}")

        return before

    if not channel_id or not group_name:
        return []

    logger.info(
        f"[AirPortCollector] starting collect air port from telegram, pages: {page_num}"
    )
    count = get_pages(channel=f"{channel_id}-{group_name}")
    if count == 0:
        return []

    pages = range(count, -1, -100)
    page_num = min(max(page_num, 1), len(pages))

    urls = [
        f"https://telemetr.io/post-list-ajax/{channel_id}?sort=-date&postType=all&period=365&before={x}"
        for x in pages[:page_num]
    ]

    cpu_count = multiprocessing.cpu_count()
    num = len(urls) if len(urls) <= cpu_count else cpu_count

    pool = multiprocessing.Pool(num)
    results = pool.map(collect_airport_page, urls)
    pool.close()

    domains = list(set(itertools.chain.from_iterable(results)))
    if not domains:
        return []

    with multiprocessing.Manager() as manager:
        availables = manager.list()
        processes = []
        semaphore = multiprocessing.Semaphore(thread_num)
        for domain in domains:
            semaphore.acquire()
            p = multiprocessing.Process(
                target=validate_domain, args=(domain, availables, semaphore)
            )
            p.start()
            processes.append(p)
        for p in processes:
            p.join()

        domains = list(availables)
        logger.info(
            f"[AirPortCollector] finished collect air port from telegram group: {group_name}, availables: {len(domain)}"
        )
        return domains


def validate_domain(url: str, availables: ListProxy, semaphore: Semaphore) -> None:
    try:
        if not url:
            return

        need_verify, invite_force, recaptcha, whitelist = AirPort.get_register_require(
            domain=url
        )
        if invite_force or recaptcha or (whitelist and need_verify):
            return

        availables.append(url)
    finally:
        if semaphore is not None and isinstance(semaphore, Semaphore):
            semaphore.release()


def crawl_single_page(url: str, push_to: list = [], exclude: str = "") -> dict:
    if not url or not push_to:
        logger.error(f"cannot crawl from page: {url}")
        return {}

    content = utils.http_get(url=url)
    if content == "":
        return {}

    return extract_subscribes(
        content=content, push_to=push_to, exclude=exclude, source=Origin.TEMPORARY.name
    )


def crawl_pages(pages: dict):
    if not pages:
        return {}

    params = []
    starttime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[PageCrawl] start crawl from Page, time: {starttime}")
    for k, v in pages.items():
        if not re.match(
            "https?://(?:[a-zA-Z0-9_\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9_\u4e00-\u9fa5\-]+.*",
            k,
        ):
            continue

        push_to = v.get("push_to", [])
        exclude = v.get("exclude", "").strip()

        params.append([k, push_to, exclude])

    subscribes = multi_thread_crawl(fun=crawl_single_page, params=params)
    endtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(
        f"[PageCrawl] finished crawl from Page, time: {endtime}, subscribes: {list(subscribes.keys())}"
    )
    return subscribes
