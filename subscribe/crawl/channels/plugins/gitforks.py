# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-04-20

import json
import math
import re
import time
from copy import deepcopy

import utils
from config.models import StorageItem, TaskParams
from crawl.channels.page import PageChannel
from crawl.helpers import fetch_jobs, is_available, naming_task
from crawl.models import ChannelResult, CrawlContext
from logger import logger
from origin import Origin
from push import PushTo
from urlvalidator import isurl

from .base import PluginContext, ScriptPlugin, register_plugin
from .commons import as_channel_result, plugin_params

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


def query_forks(username: str, repository: str, page: int, peer: int = 100, sort: str = "newest") -> dict[str, object]:
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


def collect_subs(params: dict[str, object], ctx: PluginContext | None = None) -> list[dict[str, object]]:
    def update_conf(config: dict[str, object], sub: str, name: str = "") -> dict[str, object]:
        name = naming_task(url=sub) if not name else name

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

    if ctx is not None and not isinstance(ctx, PluginContext):
        return []
    pushtool = ctx.pushtool if ctx else None
    persist = ctx.persist if ctx else None
    if not isinstance(pushtool, PushTo) or not isinstance(persist, StorageItem) or not pushtool.validate(item=persist):
        logger.error("[GithubFork] cannot fetch subscriptions due to invalid persist config")
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
    content = utils.http_get(url=pushtool.raw_url(item=persist), timeout=30)
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
                tasks.append(
                    PageChannel(url=sub, include=include, exclude=exclude, push_to=push_to, origin=Origin.PAGE.name)
                )

    # crawl all subscriptions from subscriptions.txt
    crawled = fetch_jobs(
        tasks,
        (
            ctx.crawl
            if ctx
            else CrawlContext(
                mode=0, include_nodes=True, max_fails=5, exclude="", task=TaskParams(), storage=None, pushtool=None
            )
        ),
    )
    for item in crawled.items:
        payload = deepcopy(config)
        payload.update({"sub": item.url, "saved": True})
        materials[item.url] = payload

    # check availability
    candidates = list(materials.keys())
    tasks = [[x, 2, remain, life] for x in candidates]
    masks = utils.multi_thread_run(func=is_available, tasks=tasks)

    # filter available subscriptions
    effective_subs = sorted([candidates[i] for i in range(len(masks)) if masks[i]])
    logger.info(f"[GithubFork] collect task finished, found {len(effective_subs)} subscriptions")

    # save result
    if effective_subs:
        content = "\n".join(effective_subs)
        pushtool.push_to(content=content, item=persist, group="gitfork")

    return [] if only_sublink else [materials.get(k) for k in effective_subs]


class GitForksPlugin(ScriptPlugin[dict[str, object]]):
    name = "gitforks"

    def parse(self, ctx: PluginContext) -> dict[str, object]:
        return plugin_params(ctx)

    def run(self, config: dict[str, object], ctx: PluginContext) -> ChannelResult:
        return as_channel_result(collect_subs(config, ctx))


register_plugin(GitForksPlugin())
