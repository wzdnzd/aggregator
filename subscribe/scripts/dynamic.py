# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2025-10-31

import re
from copy import deepcopy
from datetime import datetime, timedelta

import crawl
import utils
from logger import logger
from origin import Origin
from urlvalidator import isurl

# github content api prefix
GITHUB_CONTENT_API = "https://raw.githubusercontent.com"

# default branch
DEFAULT_BRANCH = "main"


def format(text: str, date: datetime = None) -> str:
    """
    Replace all time placeholders in text with current time values

    Supported placeholders:
    - {YYYY}: 4-digit year
    - {YY}: 2-digit year
    - {mm} or {mm:1} or {mm:2}: month
    - {dd} or {dd:1} or {dd:2}: day
    - {HH} or {HH:1} or {HH:2}: hour
    - {MM} or {MM:1} or {MM:2}: minute
    - {SS} or {SS:1} or {SS:2}: second

    Suffix rules:
    - No suffix or :1 - no leading zero for values < 10
    - :2 - add leading zero for values < 10
    """
    # Define the pattern for supported placeholders
    pattern = r"\{(YYYY|YY|mm|dd|HH|MM|SS)(?::(1|2))?\}"

    # Check if any placeholder exists
    if not re.search(pattern, text):
        return text

    # Get current time
    if not date or not isinstance(date, datetime):
        date = datetime.now()

    def replace(match):
        # YYYY, mm, dd, HH, MM, SS
        placeholder = match.group(1)

        # 1, 2 or None
        categroy = match.group(2)

        # Get corresponding time value
        if placeholder == "YYYY":
            value = date.year
            return str(value)
        elif placeholder == "YY":
            return str(date.year)[-2:]
        elif placeholder == "mm":
            value = date.month
        elif placeholder == "dd":
            value = date.day
        elif placeholder == "HH":
            value = date.hour
        elif placeholder == "MM":
            value = date.minute
        elif placeholder == "SS":
            value = date.second

        # Add leading zero only when format_type is '2' and value < 10
        if categroy == "2" and value < 10:
            return f"0{value}"
        else:
            return str(value)

    # Replace all matched placeholders
    result = re.sub(pattern, replace, text)
    return result


def collect_subs(params: dict) -> list[dict]:
    if not params or type(params) != dict:
        return []

    repositories = params.get("repositories", [])
    if not repositories or not isinstance(repositories, list):
        logger.error(f"[CollectSub] skip collect subscriptions due to github repositories is empty")
        return []

    config = params.get("config", {})
    if not isinstance(config, dict):
        return []

    push_to = config.get("push_to", [])
    if not push_to or not isinstance(push_to, list):
        logger.error(f"[CollectSub] cannot collect subscriptions bcause not found arguments 'push_to'")
        return []

    # github proxy server
    ghproxy = utils.trim(params.get("ghproxy", "")).removesuffix("/").lower()
    if not isurl(ghproxy):
        ghproxy = ""

    materials, sources = {}, []
    for item in repositories:
        if not item or not isinstance(item, dict) or not item.pop("enable", True):
            continue

        repository = utils.trim(item.get("repository", ""))
        if not repository or "/" not in repository or " " in repository:
            logger.warning(
                f"[CollectSub] ignore collect because {repository} is invalid, format must be username/repository"
            )
            continue

        branch = utils.trim(item.get("branch", "")) or DEFAULT_BRANCH
        prefix = f"{GITHUB_CONTENT_API}/{repository}/refs/heads/{branch}"

        single = item.get("single", False)
        include = utils.trim(item.get("include", ""))
        exclude = utils.trim(item.get("exclude", ""))

        now = datetime.now()
        yesterday = now - timedelta(days=1)

        subpath = utils.trim(item.get("subpath", ""))
        texts = set([format(text=subpath, date=date) for date in [now, yesterday]])

        for text in texts:
            url = f"{prefix}{text}" if text.startswith("/") else f"{prefix}/{text}"
            if ghproxy and url.startswith(GITHUB_CONTENT_API):
                url = f"{ghproxy}/{url}"

            if single:
                target = deepcopy(config)
                target.update({"sub": url, "saved": True})
                materials[url] = target
            else:
                sources.append([url, push_to, include, exclude, config, None, Origin.PAGE])

    if sources:
        urls = [x[0] for x in sources]
        logger.info(f"[CollectSub] start to collect subscriptions from {len(urls)} urls: {urls}")

        results = utils.multi_thread_run(func=crawl.crawl_single_page, tasks=sources)
        for result in results:
            if not result or not isinstance(result, dict):
                continue

            for k, v in result.items():
                if not k or not v or not isinstance(v, dict):
                    continue

                v.update({"sub": k, "saved": True})
                materials[k] = v

    # filter conditions
    try:
        remain = max(params.get("remain", 0), 0)
        life = max(params.get("life", 0), 0)
    except:
        logger.warning(f"[CollectSub] invalid remain or life, set to 0")
        remain, life = 0, 0

    # check availability
    candidates = list(materials.keys())
    tasks = [[x, 2, remain, life] for x in candidates]
    masks = utils.multi_thread_run(func=crawl.is_available, tasks=tasks)

    # filter available subscriptions
    subs = sorted([candidates[i] for i in range(len(masks)) if masks[i]])
    logger.info(f"[CollectSub] collect task finished, found {len(subs)} subscriptions")

    return [materials.get(k) for k in subs]
