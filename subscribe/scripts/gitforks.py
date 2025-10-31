# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-04-20

import json
import math
import re
import time
from copy import deepcopy

import crawl
import push
import utils
from logger import logger
from origin import Origin
from urlvalidator import isurl

# github rest api prefix
GITHUB_API = "https://api.github.com"

# github content api prefix
GITHUB_CONTENT_API = "https://raw.githubusercontent.com"

# proxies file path
PROXY_FILES = ["aggregate/data/proxies.yaml", "data/proxies.yaml", "data/clash.yaml"]

# subscribes file path
SUBSCRIBE_FILES = ["aggregate/data/subscribes.txt", "data/subscribes.txt"]

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
        [f"{GITHUB_CONTENT_API}/{fullname}/{DEFAULT_BRANCH}/{p}" for p in PROXY_FILES],
        [f"{GITHUB_CONTENT_API}/{fullname}/{DEFAULT_BRANCH}/{s}" for s in SUBSCRIBE_FILES],
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

            links = [f"{GITHUB_CONTENT_API}/{fullname}/{branch}/{p}" for p in PROXY_FILES]
            subs = [f"{GITHUB_CONTENT_API}/{fullname}/{branch}/{s}" for s in SUBSCRIBE_FILES]

            subscriptions[fullname] = (links, subs)
    except:
        logger.error(f"[GithubFork] cannot fetch forks for page: {page}, message: {content}")

    cost = "{:.2f}s".format(time.time() - starttime)
    logger.info(f"[GithubFork] finished query forks for page: {page}, cost: {cost}")

    return subscriptions


def collect_subs(params: dict) -> list[dict]:
    def update_conf(config: dict, sub: str, name: str = "") -> dict:
        name = crawl.naming_task(url=sub) if not name else name

        item = deepcopy(config)
        item.update({"name": name, "sub": sub, "saved": True})

        return item

    def github_warp(ghproxy: str, url: str) -> str:
        if not ghproxy or not url.startswith(GITHUB_CONTENT_API):
            return url

        return f"{ghproxy}/{url}"

    if not params or type(params) != dict:
        return []

    username = utils.trim(params.get("username", "wzdnzd"))
    repository = utils.trim(params.get("repository", "aggregator"))

    if not username or not repository:
        logger.error(f"[GithubFork] cannot list forks from github due to username or repository is empty")
        return []

    # used to store subscriptions
    storage = params.get("storage", {})
    if not storage or type(storage) != dict:
        logger.error(f"[GithubFork] cannot fetch subscriptions due to invalid storage config")
        return []

    persist = storage.get("items", {})
    pushtool = push.get_instance(config=push.PushConfig.from_dict(storage))
    if not pushtool.validate(config=persist):
        logger.error(f"[GithubFork] cannot fetch subscriptions due to invalid persist config")
        return []

    # only keep subscriptions, usually used when there are too many nodes to save to the remote service
    only_sublink = params.get("only_sublink", False)

    # github proxy server
    ghproxy = utils.trim(params.get("ghproxy", "")).removesuffix("/").lower()
    if not isurl(ghproxy):
        ghproxy = ""

    config = params.get("config", {})
    if not isinstance(config, dict) or (not only_sublink and not config.get("push_to")):
        logger.error(f"[GithubFork] cannot fetch subscriptions bcause not found arguments 'push_to'")
        return []

    materials, tasks = {}, []

    # load old subscriptions
    content = utils.http_get(url=pushtool.raw_url(config=persist), timeout=30)
    urls = re.findall(r"^https?:\/\/[^\s]+", content, flags=re.M)
    for url in urls:
        url = github_warp(ghproxy=ghproxy, url=url)
        materials[url] = update_conf(config=config, sub=url)

    whitelist, results = params.get("whitelist", []), []
    if whitelist and isinstance(whitelist, list):
        logger.info(f"[GithubFork] fetch github forks via whitelist, count: {len(whitelist)}")

        subscriptions = {}
        for fork in whitelist:
            words = utils.trim(fork).split("/")
            if len(words) != 2 and len(words) != 3:
                continue

            branch = DEFAULT_BRANCH if len(words) == 2 else words[2]
            fullname = f"{words[0]}/{words[1]}"

            links = [f"{GITHUB_CONTENT_API}/{fullname}/{branch}/{p}" for p in PROXY_FILES]
            subs = [f"{GITHUB_CONTENT_API}/{fullname}/{branch}/{s}" for s in SUBSCRIBE_FILES]
            subscriptions[fullname] = (links, subs)

        results = [subscriptions]
    else:
        # query fork list
        count, peer = query_forks_count(username=username, repository=repository, retry=3), 100
        total = int(math.ceil(count / peer))
        sort = params.get("sort", "") or "newest"

        logger.info(f"[GithubFork] fetch github forks via full scan, count: {total}")

        # see: https://docs.github.com/en/rest/repos/forks?apiVersion=2022-11-28
        if sort not in ["newest", "oldest", "stargazers", "watchers"]:
            sort = "newest"

        # concurrent fetch
        pages = [[username, repository, x, peer, sort] for x in range(1, total + 1)]
        results = utils.multi_thread_run(func=query_forks, tasks=pages)

    include = utils.trim(params.get("include", ""))
    exclude = utils.trim(params.get("exclude", ""))

    # filter conditions
    try:
        remain = max(params.get("remain", 0), 0)
        life = max(params.get("life", 0), 0)
    except:
        logger.warning(f"[GithubFork] invalid remain or life, set to 0")
        remain, life = 0, 0

    for result in results:
        if not result or type(result) != dict:
            continue

        for name, links in result.items():
            if not links or type(links) != tuple:
                continue

            name = re.sub(r"/|_", "-", name, flags=re.I).lower()
            push_to = list(set(config.get("push_to", [])))

            proxies, subs = links[0], links[1]
            for proxy in proxies:
                proxy = github_warp(ghproxy=ghproxy, url=proxy)
                materials[proxy] = update_conf(config=config, sub=proxy, name=name)
            for sub in subs:
                tasks.append([sub, push_to, include, exclude, config, None, Origin.PAGE])

    # crawl all subscriptions from subscriptions.txt
    results = utils.multi_thread_run(func=crawl.crawl_single_page, tasks=tasks)
    for result in results:
        if not result or not isinstance(result, dict):
            continue

        for k, v in result.items():
            if not k or not v or not isinstance(v, dict):
                continue

            v.update({"sub": k, "saved": True})
            materials[k] = v

    # check availability
    candidates = list(materials.keys())
    tasks = [[x, 2, remain, life] for x in candidates]
    masks = utils.multi_thread_run(func=crawl.is_available, tasks=tasks)

    # filter available subscriptions
    effective_subs = sorted([candidates[i] for i in range(len(masks)) if masks[i]])
    logger.info(f"[GithubFork] collect task finished, found {len(effective_subs)} subscriptions")

    # save result
    if effective_subs:
        content = "\n".join(effective_subs)
        pushtool.push_to(content=content, config=persist, group="gitfork")

    return [] if only_sublink else [materials.get(k) for k in effective_subs]
