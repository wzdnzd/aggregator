# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import datetime
import importlib
import itertools
import json
import multiprocessing
import os
import random
import re
import string
import sys
import time
import traceback
import typing
import urllib
import urllib.parse
import urllib.request
from copy import deepcopy
from datetime import datetime
from multiprocessing.managers import DictProxy, ListProxy
from multiprocessing.synchronize import Semaphore

import airport
import push
import utils
import yaml
from logger import logger
from origin import Origin
from urlvalidator import isurl

SEPARATOR = "-"


def multi_thread_crawl(func: typing.Callable, params: list) -> dict:
    try:
        from collections.abc import Iterable
    except ImportError:
        from collections import Iterable

    if not func or not params:
        return {}

    cpu_count = multiprocessing.cpu_count()
    num = len(params) if len(params) <= cpu_count else cpu_count

    pool = multiprocessing.Pool(num)
    if isinstance(params, Iterable):
        results = pool.starmap(func, params)
    else:
        results = pool.map(func, params)
    pool.close()

    tasks = {}
    for r in results:
        for k, v in r.items():
            item = tasks.get(k, {})
            item["origin"] = v.pop("origin", item.get("origin", ""))
            pts = item.get("push_to", [])
            pts.extend(v.pop("push_to", []))
            item["push_to"] = list(set(pts))
            item.update(v)
            tasks[k] = item

    return tasks


def batch_crawl(conf: dict, thread: int = 50) -> list:
    if not conf or not conf.get("enable", True):
        return []

    try:
        pushconf = conf.get("persist", {})
        pushtool = push.get_instance()
        should_persist = pushtool.validate(push_conf=pushconf)

        tasks, threshold = {}, conf.get("threshold", 1)
        google_spider = conf.get("google", {})
        if google_spider:
            push_to = google_spider.get("push_to", [])
            exclude = google_spider.get("exclude", "")
            tasks.update(crawl_google(qdr=7, push_to=push_to, exclude=exclude))

        github_spider = conf.get("github", {})
        if github_spider and github_spider.get("push_to", []):
            push_to = github_spider.get("push_to")
            pages = github_spider.get("pages", 1)
            exclude = github_spider.get("exclude", "")
            spams = github_spider.get("spams", [])
            tasks.update(
                crawl_github(
                    limits=pages, push_to=push_to, exclude=exclude, spams=spams
                )
            )

        telegram_spider = conf.get("telegram", {})
        if telegram_spider and telegram_spider.get("users", {}):
            users = telegram_spider.get("users")
            pages = max(telegram_spider.get("pages", 1), 1)
            tasks.update(crawl_telegram(users=users, pages=pages))

        repositories = conf.get("repositories", {})
        if repositories:
            tasks.update(crawl_github_repo(repos=repositories))

        pages = conf.get("pages", {})
        if pages:
            tasks.update(crawl_pages(pages=pages))

        scripts = conf.get("scripts", {})
        datasets, peristedtasks = [], {}
        if scripts:
            datasets = batch_call(scripts)
            if datasets:
                for item in datasets:
                    if not item or type(item) != dict or item.pop("saved", False):
                        continue

                    task = deepcopy(item)
                    subs = task.pop("sub", None)
                    if type(subs) not in [str, list]:
                        continue
                    if type(subs) == str:
                        subs = [subs]
                    for sub in subs:
                        if utils.isblank(sub):
                            continue
                        remark(source=task, defeat=0, discovered=True)
                        peristedtasks[sub] = task

        if should_persist:
            folderid = pushconf.get("folderid", "")
            fileid = pushconf.get("fileid", "")
            username = pushconf.get("username", "")
            url = pushtool.raw_url(fileid=fileid, folderid=folderid, username=username)
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
                        merged = dict(list(v.items()) + list(tasks.get(k, {}).items()))
                        tasks[k] = merged
            except:
                logger.error("[CrawlError] load old subscriptions from remote error")
                pass

        if not tasks:
            logger.debug(
                "[CrawlInfo] cannot found any subscribe from Google/Telegram/Github and Page with crawler"
            )
            return datasets

        exclude = conf.get("exclude", "")
        taskconf = conf.get("config", {})
        with multiprocessing.Manager() as manager:
            availables, unknowns, potentials = (
                manager.list(),
                manager.list(),
                manager.dict(),
            )
            processes = []
            semaphore = multiprocessing.Semaphore(max(thread, 1))
            time.sleep(random.randint(1, 3))
            for key, value in tasks.items():
                for k, v in taskconf.items():
                    if k not in value:
                        value[k] = v

                semaphore.acquire()
                p = multiprocessing.Process(
                    target=validate,
                    args=(
                        key,
                        value,
                        availables,
                        unknowns,
                        potentials,
                        semaphore,
                        exclude,
                        threshold,
                    ),
                )
                p.start()
                processes.append(p)
            for p in processes:
                p.join()

            datasets.extend(list(availables))
            peristedtasks.update(dict(potentials))

            if len(unknowns) > 0:
                logger.warn(
                    f"[CrawlWarn] some links were found, but could not be confirmed to work, subscriptions: {list(unknowns)}"
                )

        logger.info(f"[CrawlInfo] crawl finished, found {len(datasets)} subscribes")

        if should_persist and peristedtasks:
            content = json.dumps(peristedtasks)
            pushtool.push_to(content=content, push_conf=pushconf, group="crwal")

        return datasets
    except:
        logger.error("[CrawlError] crawl from web error")
        traceback.print_exc()
        return []


def generate_telegram_task(channel: str, config: dict, pages: int, limits: int):
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
    return [
        [f"https://t.me/s/{channel}?before={x}", pts, include, exclude, limits, params]
        for x in arrays[:pages]
    ]


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
    starttime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[TelegramCrawl] start crawl from Telegram, time: {starttime}")

    params = [[k, v, pages, limits] for k, v in users.items()]
    cpu_count = multiprocessing.cpu_count()
    num = len(params) if len(params) <= cpu_count else cpu_count

    pool = multiprocessing.Pool(num)
    results = pool.starmap(generate_telegram_task, params)
    pool.close()

    tasks = list(itertools.chain.from_iterable(results))
    subscribes = multi_thread_crawl(func=crawl_telegram_page, params=tasks)
    endtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[TelegramCrawl] finished crawl from Telegram, time: {endtime}")
    logger.debug(f"[TelegramCrawl] subscriptions: {list(subscribes.keys())}")
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
        logger.error(
            f"[GithubCrawl] crawl from github error, username: {username}\trepo: {repo}"
        )
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

    subscribes = multi_thread_crawl(func=crawl_single_repo, params=params)
    endtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[RepoCrawl] finished crawl from Repositorie, time: {endtime}")
    logger.debug(f"[RepoCrawl] subscriptions: {list(subscribes.keys())}")
    return subscribes


def crawl_google(
    qdr: int = 10,
    push_to: list = [],
    exclude: str = "",
    limits: int = 100,
    interval: int = 0,
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
            try:
                if exclude and re.search(exclude, s):
                    continue
                collections[s] = {"push_to": push_to, "origin": Origin.GOOGLE.name}
            except:
                continue

        time.sleep(interval)

    endtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[GoogleCrawl] finished crawl from Google, time: {endtime}")
    logger.debug(f"[GoogleCrawl] subscriptions: {list(collections.keys())}")
    return collections


def crawl_github_page(
    page: int, cookie: str, push_to: list = [], exclude: str = ""
) -> dict:
    content = search_github_code(page=page, cookie=cookie)
    return extract_subscribes(
        content=content, push_to=push_to, exclude=exclude, source=Origin.GITHUB.name
    )


def search_github(page: int, cookie: str, searchtype: str, sortedby: str) -> str:
    if page <= 0 or utils.isblank(cookie):
        return ""

    searchtype = "Code" if utils.isblank(searchtype) else searchtype
    sortedby = "indexed" if utils.isblank(sortedby) else sortedby

    url = f"https://github.com/search?o=desc&p={page}&q=%22%2Fapi%2Fv1%2Fclient%2Fsubscribe%3Ftoken%3D%22&s={sortedby}&type={searchtype}"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Referer": "https://github.com",
        "User-Agent": utils.USER_AGENT,
        "Cookie": f"user_session={cookie}",
    }
    content = utils.http_get(url=url, headers=headers)
    if re.search(r"<h1>Sign in to GitHub</h1>", content, flags=re.I):
        logger.error(
            "[GithubCrawl] session has expired, please provide a valid session and try again"
        )
        return ""

    return content


def paging(start: int, end: int, peer_page: int) -> list[int]:
    if start > end or peer_page <= 0:
        return []

    pages = []
    for i in range(start, end + 1, peer_page):
        pages.append(i // peer_page + 1)

    return pages


def search_github_issues(page: int, cookie: str) -> list:
    content = search_github(
        page=page, cookie=cookie, searchtype="Issues", sortedby="created"
    )
    if utils.isblank(content):
        return []

    try:
        regex = 'href="(/.*/.*/issues/\d+)">'
        groups = re.findall(regex, content, flags=re.I)
        links = list(set(groups))
        links = [f"https://github.com{x}" for x in links]
        return links
    except:
        return []


def search_github_issues_byapi(peer_page: int = 50, page: int = 1) -> list:
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


def search_github_code_byapi(
    token: str, peer_page: int = 50, page: int = 1, excludes: list = []
) -> list:
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

            reponame = item.get("repository", {}).get("full_name", "")
            if not intercept(text=reponame, excludes=excludes):
                links.add(link)

        return list(links)
    except:
        return []


def search_github_code(page: int, cookie: str, excludes: list = []) -> list:
    content = search_github(
        page=page, cookie=cookie, searchtype="Code", sortedby="indexed"
    )
    if utils.isblank(content):
        return []

    try:
        regex = '<a href="(/.*/.*/blob/.*)#L\d+">\d+</a>'
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


def batchextract_github_pages(func: typing.Callable, params: list) -> list:
    if not func or not params or type(params) != list:
        return []

    cpu_count = multiprocessing.cpu_count()
    num = len(params) if len(params) <= cpu_count else cpu_count

    pool = multiprocessing.Pool(num)
    results = pool.starmap(func, params)
    pool.close()
    return list(set(itertools.chain.from_iterable(results)))


def crawl_github(
    limits: int = 3, push_to: list = [], spams: list = [], exclude: str = ""
) -> dict:
    # user_session=${any}
    cookie = os.environ.get("GH_COOKIE", "").strip()
    token = os.environ.get("GH_TOKEN", "").strip()
    if utils.isblank(cookie) and utils.isblank(token):
        logger.error(
            "[GithubCrawl] cannot start crawl from github because cookie and token is missing"
        )
        return {}

    links, starttime = [], datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    method = "search on the page" if utils.isblank(token) else "rest api"
    logger.info(
        f"[GithubCrawl] start crawl from Github through {method}, time: {starttime}"
    )

    if utils.isblank(token):
        # 鉴于github搜索code不稳定，爬取两次
        pages = [x for x in range(1, limits + 1)] * 2
        params = [[x, cookie, spams] for x in pages]

        links.extend(batchextract_github_pages(func=search_github_code, params=params))
        links.extend(search_github_issues(page=1, cookie=cookie))
    else:
        peer_page, count = 50, 10
        pages = paging(start=0, end=limits * count + 1, peer_page=peer_page)
        params = [[token, peer_page, x, spams] for x in pages] * 2
        links.extend(
            batchextract_github_pages(func=search_github_code_byapi, params=params)
        )
        links.extend(search_github_issues_byapi(peer_page=5, page=1))

    if links:
        page_tasks = {}
        exclude = "" if not exclude else exclude.strip()

        for link in links:
            page_tasks[link] = {"push_to": push_to, "exclude": exclude}
        subscribes = crawl_pages(pages=page_tasks, silent=True)
    else:
        subscribes = {}
        logger.error(
            "[GithubCrawl] cannot found any links for [/api/v1/client/subscribe?token=]"
        )

    endtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[GithubCrawl] finished crawl from Github, time: {endtime}")
    logger.debug(f"[GithubCrawl] subscriptions: {list(subscribes.keys())}")

    return subscribes


def crawl_single_page(
    url: str, push_to: list = [], exclude: str = "", config: dict = {}
) -> dict:
    if not url or not push_to:
        logger.error(f"[PageCrawl] cannot crawl from page: {url}")
        return {}

    content = utils.http_get(url=url)
    if content == "":
        return {}

    return extract_subscribes(
        content=content,
        push_to=push_to,
        exclude=exclude,
        source=Origin.TEMPORARY.name,
        config=config,
    )


def crawl_pages(pages: dict, silent: bool = False) -> dict:
    if not pages:
        return {}

    params = []
    starttime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not silent:
        logger.info(f"[PageCrawl] start crawl from Page, time: {starttime}")

    for k, v in pages.items():
        if not isurl(url=k):
            continue

        push_to = v.get("push_to", [])
        exclude = v.get("exclude", "").strip()
        config = v.get("config", {})

        params.append([k, push_to, exclude, config])

    subscribes = multi_thread_crawl(func=crawl_single_page, params=params)
    endtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not silent:
        logger.info(f"[PageCrawl] finished crawl from Page, time: {endtime}")
        logger.debug(f"[PageCrawl] subscriptions: {list(subscribes.keys())}")

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
) -> dict:
    if not content:
        return {}
    try:
        limits, collections = max(1, limits), {}
        regex = "https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+(?:(?:(?:/index.php)?/api/v1/client/subscribe\?token=[a-zA-Z0-9]{16,32})|(?:/link/[a-zA-Z0-9]+\?(?:sub|mu|clash)=\d))"

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

        # 去重会打乱原本按日期排序的特性一致无法优先选择离当前时间较近的元素
        # subscribes = list(set(subscribes))

        if reversed:
            subscribes.reverse()

        for s in subscribes:
            try:
                if include and not re.match(
                    "https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+.*",
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
            # s = s.replace("http://", "https://", 1).strip()
            params = {"push_to": push_to, "origin": source}
            if config:
                params.update(config)
            collections[s] = params

            if len(collections) >= limits:
                break

        return collections
    except:
        logger.error("[ExtractError] extract subscribe error")
        return {}


def validate(
    url: str,
    params: dict,
    availables: ListProxy,
    unknows: ListProxy,
    potentials: DictProxy,
    semaphore: Semaphore,
    exclude: str = "",
    threshold: int = 1,
) -> None:
    try:
        if (
            not params
            or not params.get("push_to", None)
            or not params.get("origin", "")
            or (exclude and re.search(exclude, url))
        ):
            return

        threshold = max(threshold, 1)
        defeat = params.get("defeat", 0) + 1
        discovered = params.get("discovered", False)

        reachable, expired = check_status(url=url, retry=2, remain=5, spare_time=12)
        if reachable:
            item = {"name": naming_task(url), "sub": url, "debut": True}
            item.update(params)
            availables.append(item)
            # reset defeat to 0
            defeat = 0
            discovered = True

        if params.pop("saved", False):
            return

        if reachable or (discovered and defeat <= threshold and not expired):
            remark(source=params, defeat=defeat, discovered=True)
            potentials[url] = params
        elif not expired:
            unknows.append(url)
    finally:
        if semaphore is not None and isinstance(semaphore, Semaphore):
            semaphore.release()


def remark(source: dict, defeat: int = 0, discovered: bool = True) -> None:
    if (
        not source
        or type(source) != dict
        or type(defeat) != int
        or defeat < 0
        or type(discovered) != bool
    ):
        return

    source["defeat"] = defeat
    source["discovered"] = discovered
    if utils.isblank(source.get("origin", "")):
        source["origin"] = Origin.TEMPORARY.name


def check_status(
    url: str, retry: int = 2, remain: float = 0, spare_time: float = 0
) -> tuple[bool, bool]:
    """
    url: subscription link
    retry: number of retries
    remain: minimum remaining traffic flow
    spare_time: minimum remaining time
    """
    if not url or retry <= 0:
        return False, False

    remain, spare_time = max(0, remain), max(spare_time, 0)
    try:
        headers = {"User-Agent": "ClashforWindows"}
        request = urllib.request.Request(url=url, headers=headers)
        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
        if response.getcode() != 200:
            return False, False

        # 根据订阅信息判断是否有效
        try:
            subscription = response.getheader("subscription-userinfo")
            if subscription:
                infos = subscription.split(";")
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
                return flag, not flag
        except:
            pass

        content = str(response.read(), encoding="utf8")
        if utils.isblank(content):
            return False, True
        elif utils.isb64encode(content):
            return True, False

        # return re.search("proxies:", content) is not None, False
        try:
            proxies = yaml.load(content, Loader=yaml.SafeLoader).get("proxies", [])
        except yaml.constructor.ConstructorError:
            yaml.add_multi_constructor(
                "str", lambda loader, suffix, node: None, Loader=yaml.SafeLoader
            )
            proxies = yaml.load(content, Loader=yaml.FullLoader).get("proxies", [])
        except:
            proxies = []

        flag = proxies is None or len(proxies) == 0
        return not flag, flag
    except urllib.error.HTTPError as e:
        message = str(e.read(), encoding="utf8")
        expired = e.code == 404 or "token is error" in message
        if not expired and e.code in [403, 503]:
            return check_status(
                url=url, retry=retry - 1, remain=remain, spare_time=spare_time
            )

        return False, expired
    except Exception as e:
        return check_status(
            url=url, retry=retry - 1, remain=remain, spare_time=spare_time
        )


def is_available(
    url: str, retry: int = 2, remain: float = 0, spare_time: float = 0
) -> bool:
    available, _ = check_status(
        url=url, retry=retry, remain=remain, spare_time=spare_time
    )
    return available


def naming_task(url):
    prefix = utils.extract_domain(url=url).replace(".", "") + SEPARATOR
    return prefix + "".join(
        random.sample(string.digits + string.ascii_lowercase, random.randint(3, 5))
    )


def get_telegram_pages(channel: str) -> int:
    if not channel or channel.strip() == "":
        return 0

    url = f"https://t.me/s/{channel}"
    content = utils.http_get(url=url)
    before = 0
    try:
        regex = f'<link\s+rel="canonical"\s+href="/s/{channel}\?before=(\d+)">'
        groups = re.findall(regex, content)
        before = int(groups[0]) if groups else before
    except:
        logger.error(f"[CrawlError] cannot count page num, chanel: {channel}")

    return before


def extract_airport_site(url: str) -> list:
    if not url:
        return []

    logger.info(f"[AirPortCrawl] start collect airport, url: {url}")

    content = utils.http_get(url=url)
    if not content:
        logger.error(f"[CrawlError] cannot any content from url: {url}")
        return []
    try:
        regex = 'href="(https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+/?)"\s+target="_blank"\s+rel="noopener">'
        groups = re.findall(regex, content)
        return list(set(groups)) if groups else []
    except:
        return []


def crawl_channel(channel: str, page_num: int, fun: typing.Callable) -> list:
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
        logger.info(
            f"[TelegramCrawl] starting crawl from telegram, channel: {channel}, pages: {page_num}"
        )

        urls = [f"{url}?before={x}" for x in pages[:page_num]]
        cpu_count = multiprocessing.cpu_count()
        num = len(urls) if len(urls) <= cpu_count else cpu_count

        pool = multiprocessing.Pool(num)
        results = pool.map(fun, urls)
        pool.close()

        return list(itertools.chain.from_iterable(results))


def collect_airport(channel: str, page_num: int, thread_num: int = 50) -> list:
    domains = crawl_channel(
        channel=channel, page_num=page_num, fun=extract_airport_site
    )

    if not domains:
        return []

    with multiprocessing.Manager() as manager:
        availables = manager.list()
        processes = []
        semaphore = multiprocessing.Semaphore(thread_num)
        for domain in list(set(domains)):
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
            f"[AirPortCollector] finished collect air port from telegram channel: {channel}, availables: {len(domain)}"
        )
        return domains


def validate_domain(url: str, availables: ListProxy, semaphore: Semaphore) -> None:
    try:
        if not url:
            return

        rr = airport.AirPort.get_register_require(domain=url)

        # if rr.invite or rr.recaptcha:
        if rr.invite or rr.recaptcha or (rr.whitelist and rr.verify):
            return

        availables.append(url)
    finally:
        if semaphore is not None and isinstance(semaphore, Semaphore):
            semaphore.release()


def batch_call(tasks: dict) -> list:
    if not tasks:
        return []

    try:
        thread_num = max(min(len(tasks), 50), 1)
        with multiprocessing.Manager() as manager:
            availables = manager.list()
            processes = []
            semaphore = multiprocessing.Semaphore(thread_num)
            time.sleep(random.randint(1, 3))
            for k, v in tasks.items():
                semaphore.acquire()
                p = multiprocessing.Process(
                    target=call, args=(k, v, availables, semaphore)
                )
                p.start()
                processes.append(p)
            for p in processes:
                p.join()

            return list(availables)
    except:
        traceback.print_exc()
        return []


def call(
    script: str, params: dict, availables: ListProxy, semaphore: Semaphore
) -> None:
    try:
        if not script:
            return

        subscribes = execute_script(script=script, params=params)
        if subscribes and type(subscribes) == list:
            availables.extend(subscribes)
    finally:
        if semaphore is not None and isinstance(semaphore, Semaphore):
            semaphore.release()


def execute_script(script: str, params: dict = {}) -> list:
    try:
        # format: a.b.c#function or a-b.c#_function or a#function and so on
        regex = r"^([a-zA-Z0-9_]+|([0-9a-zA-Z_]+([a-zA-Z0-9_\-]+)?\.)+)[a-zA-Z0-9_\-]+#[a-zA-Z_]+[0-9a-zA-Z_]+$"
        if not re.match(regex, script):
            logger.info(
                f"[ScriptError] script execute error because script: {script} is invalidate"
            )
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
            logger.error(
                f"[ScriptError] return value error, need a list, but got a {type(subscribes)}"
            )
            return []

        endtime = time.time()
        logger.info(
            "[ScriptInfo] finished execute script: scripts.{}, cost: {:.3}s".format(
                script, endtime - starttime
            )
        )

        subscribes = [s for s in subscribes if type(s) == dict and s.get("push_to", [])]
        return subscribes
    except:
        logger.error(
            f"[ScriptError] occur error run script: {script}, message: \n{traceback.format_exc()}"
        )
        return []
