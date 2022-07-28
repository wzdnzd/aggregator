# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import datetime
import multiprocessing
import random
import re
import string
import time
from multiprocessing.managers import ListProxy

import utils


def batch_crawl(conf: dict, period: int, thread: int = 50) -> list:
    if not conf:
        return []

    params = [[k, period, v] for k, v in conf.items()]
    cpu_count = multiprocessing.cpu_count()
    num = len(params) if len(params) <= cpu_count else cpu_count

    pool = multiprocessing.Pool(num)
    results = pool.starmap(crawl_telegram, params)
    pool.close()

    tasks = {}
    for r in results:
        for k, v in r.items():
            items = tasks.get(k, [])
            items.extend(v)
            tasks[k] = list(set(items))

    if not tasks:
        print("cannot any subscribe url from telegram")
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


def crawl_telegram(
    userid: str, period: int, push_to: list = [], limits: int = 20
) -> dict:
    if not userid:
        return {}

    now = time.time() - 3600 * 12
    crawl_time = datetime.datetime.fromtimestamp(now).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"https://telemetr.io/post-list-ajax/{userid}/with-date-panel?period={period}&date={crawl_time}"

    content = utils.http_get(url=url)
    if content == "":
        return {}

    regex = "https?://\S+/api/v1/client/subscribe\?token=[a-zA-Z0-9]+|https?://\S+/link/[a-zA-Z0-9]+\?sub=\d"
    subscribes = re.findall(regex, content)

    collections = {}
    for s in subscribes:
        # 强制使用https协议
        s = s.replace("http://", "https://", 1)

        if "token=" in s:
            s += "&flag=v2ray"
        collections[s] = push_to
        if len(collections) >= limits:
            break

    return collections


def validate_available(
    url: str, push_to: list, availables: ListProxy, semaphore: multiprocessing.Semaphore
) -> None:
    if utils.http_get(url=url, retry=2) != "":
        item = {"name": naming_task(url), "sub": url, "push_to": push_to}
        availables.append(item)

    semaphore.release()


def naming_task(url):
    prefix = utils.extract_domain(url=url).replace(".", "")
    return prefix + "".join(
        random.sample(string.digits + string.ascii_lowercase, random.randint(3, 5))
    )
