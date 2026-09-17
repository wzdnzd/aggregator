# -*- coding: utf-8 -*-

import json
import time

import utils
from config.models import RepoConfig, TaskParams
from crawl.base import Channel, register_channel
from crawl.extract import extract_subscribes
from crawl.helpers import merge_results
from crawl.models import ChannelResult, CrawlContext
from logger import logger
from origin import Origin


class RepositoryChannel(Channel[list[RepoConfig]]):
    name = "repositories"

    def crawl(self, config: list[RepoConfig], ctx: CrawlContext) -> ChannelResult:
        return crawl_github_repo(config, ctx)


def crawl_single_repo(
    username: str, repo: str, push_to: list[str], commits: int, exclude: str, include_nodes: bool
) -> ChannelResult:
    if not username or not repo:
        logger.error(f"cannot crawl from github, username: {username}\trepo: {repo}")
        return ChannelResult()

    commits = max(1, commits)
    url = f"https://api.github.com/repos/{username.strip()}/{repo.strip()}/commits?per_page={commits}"
    content = utils.http_get(url=url)
    if not content:
        return ChannelResult()

    result = ChannelResult()
    task = TaskParams(push_to=list(push_to))
    try:
        records = json.loads(content)
        for item in records:
            payload = utils.http_get(url=item.get("url", ""))
            if not payload:
                continue
            commit = json.loads(payload)
            for file in commit.get("files", []):
                result.merge(
                    extract_subscribes(
                        content=file.get("patch", ""),
                        push_to=push_to,
                        source=Origin.REPO.name,
                        exclude=exclude,
                        task=task,
                        include_nodes=include_nodes,
                    )
                )
        return result
    except Exception:
        logger.error(f"[GithubCrawl] crawl from github error, username: {username}\trepo: {repo}")
        return ChannelResult()


def crawl_github_repo(repos: list[RepoConfig], ctx: CrawlContext) -> ChannelResult:
    if not repos:
        return ChannelResult()

    starttime = time.time()
    params = []
    for item in repos:
        if not item.enable:
            continue
        username = utils.trim(item.username)
        repo = utils.trim(item.repo)
        if not username or not repo or not item.push_to:
            continue
        params.append([username, repo, item.push_to, max(item.commits, 1), item.exclude, ctx.include_nodes])

    results = utils.multi_thread_run(func=crawl_single_repo, tasks=params, num_threads=ctx.num_threads)
    result = merge_results(results)
    logger.info(
        f"[RepoCrawl] finished crawl from Repositorie, found {len(result.items)} subscriptions, cost: {time.time() - starttime:.2f}s"
    )
    return result


register_channel(RepositoryChannel())
