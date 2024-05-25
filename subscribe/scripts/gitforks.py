# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-04-20

import json
import math
import re
import time
from copy import deepcopy

import crawl
import utils
from logger import logger
from origin import Origin

# github rest api prefix
GITHUB_API = "https://api.github.com"

# github content api prefix
GITHUB_CONTENT_API = "https://raw.githubusercontent.com"

# proxies file path
PROXIES_FILE = "aggregate/data/proxies.yaml"

# subscribes file path
SUBSCRIBES_FILE = "aggregate/data/subscribes.txt"

# default branch
DEFAULT_BRANCH = "main"

# github request headers
DEFAULT_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": utils.USER_AGENT,
}


def query_forks_count(username: str, repository: str, retry: int = 3) -> int:
    username = utils.trim(username)
    repository = utils.trim(repository)
    if not username or not repository:
        logger.error(f"[GithubFork] invalid github username or repository")
        return -1

    url = f"{GITHUB_API}/repos/{username}/{repository}"
    content = utils.http_get(url=url, headers=DEFAULT_HEADERS, retry=retry)
    if not content:
        logger.error(f"[GithubFork] failed to query forks count")
        return -1

    try:
        data = json.loads(content)
        return data.get("forks_count", 0)
    except:
        logger.error(f"[GithubFork] occur error when parse forks count, message: {content}")
        return -1


def query_forks(username: str, repository: str, page: int, peer: int = 100, sort: str = "newest") -> dict:
    username = utils.trim(username)
    repository = utils.trim(repository)

    if not username or not repository or page <= 0:
        return {}

    peer = min(max(peer, 1), 100)
    url = f"{GITHUB_API}/repos/{username}/{repository}/forks?sort={sort}&per_page={peer}&page={page}"

    fullname = f"{username}/{repository}"
    source = (
        f"{GITHUB_CONTENT_API}/{fullname}/{DEFAULT_BRANCH}/{PROXIES_FILE}",
        f"{GITHUB_CONTENT_API}/{fullname}/{DEFAULT_BRANCH}/{SUBSCRIBES_FILE}",
    )
    subscriptions, starttime = {fullname: source}, time.time()

    content, retry = "", 5
    while not content and retry > 0:
        content = utils.http_get(url=url, headers=DEFAULT_HEADERS, interval=1.0)
        retry -= 1
        if not content:
            time.sleep(2)

    try:
        data = json.loads(content)
        for fork in data:
            if not fork or type(fork) != dict:
                continue

            fullname = fork.get("full_name", "")
            branch = fork.get("default_branch", DEFAULT_BRANCH)

            link = f"{GITHUB_CONTENT_API}/{fullname}/{branch}/{PROXIES_FILE}"
            sub = f"{GITHUB_CONTENT_API}/{fullname}/{branch}/{SUBSCRIBES_FILE}"

            subscriptions[fullname] = (link, sub)
    except:
        logger.error(f"[GithubFork] cannot fetch forks for page: {page}, message: {content}")

    cost = "{:.2f}s".format(time.time() - starttime)
    logger.info(f"[GithubFork] finished query forks for page: {page}, cost: {cost}")

    return subscriptions


def collect_subs(params: dict) -> list[dict]:
    if not params or type(params) != dict:
        return []

    config = params.get("config", {})
    if not config or not isinstance(config, dict) or not config.get("push_to"):
        logger.error(f"[GithubFork] cannot fetch subscribes bcause not found arguments 'push_to'")
        return []

    username = utils.trim(params.get("username", "wzdnzd"))
    repository = utils.trim(params.get("repository", "aggregator"))

    if not username or not repository:
        logger.error(f"[GithubFork] cannot list forks from github due to username or repository is empty")
        return []

    count, peer = query_forks_count(username=username, repository=repository, retry=3), 100
    total = int(math.ceil(count / peer))

    sort = params.get("sort", "") or "newest"

    # see: https://docs.github.com/en/rest/repos/forks?apiVersion=2022-11-28
    if sort not in ["newest", "oldest", "stargazers", "watchers"]:
        sort = "newest"

    # concurrent
    tasks = [[username, repository, x, peer, sort] for x in range(1, total + 1)]
    results = utils.multi_thread_run(func=query_forks, tasks=tasks)

    nocache = params.get("nocache", False)
    include = utils.trim(params.get("include", ""))
    exclude = utils.trim(params.get("exclude", ""))

    # filter conditions
    try:
        remain = max(params.get("remain", 0), 0)
        life = max(params.get("life", 0), 0)
    except:
        logger.warning(f"[GithubFork] invalid remain or life, set to 0")
        remain, life = 0, 0

    items, tasks = [], []
    for result in results:
        if not result or type(result) != dict:
            continue

        for name, links in result.items():
            if not links or type(links) != tuple:
                continue

            name = re.sub(r"/|_", "-", name, flags=re.I).lower()
            push_to = list(set(config.get("push_to")))

            proxy, sub = links[0], links[1]
            if proxy:
                item = deepcopy(config)
                item.update({"name": name, "sub": proxy, "push_to": push_to, "saved": True})

                items.append(item)
            if sub:
                tasks.append([sub, push_to, include, exclude, config, None, Origin.PAGE, nocache])

    # filter available proxies links
    checks = [[x["sub"], 2, remain, life] for x in items]
    masks = utils.multi_thread_run(func=crawl.is_available, tasks=checks)
    items = [items[i] for i in range(len(items)) if masks[i]]

    # crawl all subscriptions from subscriptions.txt
    results = utils.multi_thread_run(func=crawl.crawl_single_page, tasks=tasks)
    links, candidates = [], []
    for result in results:
        if not result or not isinstance(result, dict):
            continue

        for k, v in result.items():
            if not k or not v or not isinstance(v, dict):
                continue

            v["sub"] = k
            links.append(k)
            candidates.append(v)

    if not nocache and (remain > 0 or life > 0):
        tasks = [[x, 2, remain, life] for x in links]
        masks = utils.multi_thread_run(func=crawl.is_available, tasks=tasks)

        latest = list()
        for i in range(len(candidates)):
            candidate = candidates[i]
            candidate["checked"] = masks[i]
            if not masks[i]:
                candidate["nocache"] = True

            latest.append(candidate)
    else:
        latest = candidates

    items.extend(latest)
    return items
