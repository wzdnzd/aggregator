# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-09-08

import itertools
import re
import sys
import time
from copy import deepcopy

import utils
from crawl import naming_task
from logger import logger
from origin import Origin


def search(exclude: str = "", maxsize: int = sys.maxsize, timesleep: float = 3, timeout: float = 180) -> list[str]:
    try:
        from fofa_hack import fofa as client
    except ImportError:
        logger.error(
            "[FOFA] please make sure that the dependencies pycryptodomex and fofa-hack are installed correctly"
        )
        return []

    exclude = utils.trim(exclude)
    maxsize = max(maxsize, 10)
    timesleep = max(timesleep, 0)
    timeout = max(timeout, 0)
    items = set()

    generator = client.api(
        search_key='body="port: 7890" && body="socks-port: 7891" && body="allow-lan: true"',
        endcount=maxsize,
        timesleep=timesleep,
        timeout=timeout,
    )

    for data in generator:
        if not data:
            break

        for site in data:
            url = utils.trim(site)
            try:
                if url and (not exclude or not re.search(exclude, url, flags=re.I)):
                    items.add(url)
            except:
                logger.error(f"[FOFA] invalid pattern: {exclude}")

    return list(items)


def extract_one(url: str) -> list[str]:
    headers = {"User-Agent": "Clash.Meta; Mihomo"}
    content = utils.http_get(url=url, headers=headers, timeout=15)

    subscriptions = []
    if content:
        regex = r"(?:https?://)?(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+(?:(?:(?:/index.php)?/api/v1/client/subscribe\?token=[a-zA-Z0-9]{16,32})|(?:/link/[a-zA-Z0-9]+\?(?:sub|mu|clash)=\d))"
        groups = re.findall(regex, content, flags=re.I)

        if groups:
            subscriptions = list(set([utils.url_complete(x) for x in groups if x]))

    return subscriptions


def recall(params: dict) -> list:
    if not params or type(params) != dict:
        return []

    exclude = params.get("exclude", "")
    check = params.get("check", True)
    maxsize = int(params.get("maxsize", sys.maxsize))
    timesleep = float(params.get("timesleep", 3))
    timeout = float(params.get("timeout", 180))

    starttime = time.time()
    links = search(exclude=exclude, maxsize=maxsize, timesleep=timesleep, timeout=timeout)
    if not links:
        logger.error(f"[FOFA] cannot found any valid public subscription, cost: {time.time()-starttime:.2f}s")
        return []

    tasks = list()
    for link in links:
        config = deepcopy(params.get("config", {}))
        config["sub"] = link
        config["saved"] = True
        config["name"] = naming_task(link)
        config["push_to"] = list(set(config.get("push_to", [])))

        tasks.append(config)

    if check:
        logger.info(f"[FOFA] start to extract subscription from links, count: {len(links)}")

        results = utils.multi_process_run(func=extract_one, tasks=links)
        subscriptions = [x for x in set(itertools.chain.from_iterable(results)) if x]

        for item in subscriptions:
            config = deepcopy(params.get("config", {}))
            config["sub"] = item
            config["checked"] = False
            config["saved"] = False
            config["origin"] = Origin.FOFA.name
            config["name"] = naming_task(item)
            config["push_to"] = list(set(config.get("push_to", [])))

            tasks.append(config)

        logger.info(f"[FoFA] found {len(subscriptions)} subscriptions: {subscriptions}")

    cost = "{:.2f}s".format(time.time() - starttime)
    logger.info(f"[FOFA] search finished, found {len(tasks)} candidates to be check, cost: {cost}")

    return tasks
