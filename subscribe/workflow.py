# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import json
import os
import re
from dataclasses import dataclass, field

import renewal
import utils
from airport import ANOTHER_API_PREFIX, AirPort
from config.models import NodeInput, ProcessConfig, RenewJob, SiteConfig
from logger import logger
from origin import Origin
from push import PushTo


@dataclass
class TaskConfig:
    name: str
    bin_name: str
    taskid: int = -1
    domain: str = ""
    nodes: NodeInput = field(default_factory=NodeInput)
    index: int = 1
    retry: int = 3
    max_rate: float = 20.0
    renew: RenewJob | None = None
    coupon: str = ""
    rename: str = ""
    exclude: str = ""
    include: str = ""
    check_alive: bool = True
    require_tls: bool = False
    ignore_default_exclude: bool = False
    special_protocols: bool = False
    allow_gmail_alias: bool = False
    skip_captcha: bool = False
    invite_code: str = ""
    api_prefix: str = "/api/v1/"


def execute(task_conf: TaskConfig) -> list[dict[str, object]]:
    if not task_conf or not isinstance(task_conf, TaskConfig):
        return []

    obj = AirPort(
        name=task_conf.name,
        site=task_conf.domain,
        nodes=task_conf.nodes,
        rename=task_conf.rename,
        exclude=task_conf.exclude,
        include=task_conf.include,
        check_alive=task_conf.check_alive,
        coupon=task_conf.coupon,
        api_prefix=task_conf.api_prefix,
    )

    logger.info(f"start fetch proxy: name=[{task_conf.name}]\tid=[{task_conf.index}]\tdomain=[{obj.ref}]")

    # 套餐续期
    if task_conf.renew:
        sub_url = renewal.add_traffic_flow(
            domain=obj.ref,
            job=task_conf.renew,
            jsonify=obj.api_prefix == ANOTHER_API_PREFIX,
        )
        if sub_url and not obj.registed:
            obj.registed = True
            obj.nodes.subscribe = sub_url

    cookie, authorization = "", ""
    if task_conf.nodes.empty() and task_conf.domain:
        cookie, authorization = obj.get_subscribe(
            retry=task_conf.retry,
            allow_gmail_alias=task_conf.allow_gmail_alias,
            skip_captcha=task_conf.skip_captcha,
            invite_code=task_conf.invite_code,
        )

    proxies = obj.parse(
        cookie=cookie,
        auth=authorization,
        retry=task_conf.retry,
        rate=task_conf.max_rate,
        bin_name=task_conf.bin_name,
        require_tls=task_conf.require_tls,
        ignore_exclude=task_conf.ignore_default_exclude,
        special_protocols=task_conf.special_protocols,
        nodes=task_conf.nodes,
    )

    logger.info(
        f"finished fetch proxy: name=[{task_conf.name}]\tid=[{task_conf.index}]\tdomain=[{obj.ref}]\tcount=[{len(proxies)}]"
    )

    return proxies


def executewrapper(task_conf: TaskConfig) -> tuple[int, list[dict[str, object]]]:
    if not task_conf:
        return (-1, [])

    taskid = task_conf.taskid
    proxies = execute(task_conf=task_conf)
    return (taskid, proxies)


def liveness_fillter(proxies: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not list:
        return [], []

    checks, nochecks = [], []
    for p in proxies:
        if not isinstance(p, dict):
            continue

        liveness = p.pop("liveness", True)
        if liveness:
            checks.append(p)
        else:
            p.pop("sub", "")
            nochecks.append(p)

    return checks, nochecks


def cleanup(filepath: str = "", filenames: list[str] | None = None) -> None:
    if not filepath or not filenames:
        return

    for name in filenames:
        filename = os.path.join(filepath, name)
        if os.path.exists(filename):
            os.remove(filename)


def dedup_task(tasks: list[TaskConfig]) -> list[TaskConfig]:
    if not tasks:
        return []
    items = []
    for task in tasks:
        if not exists(tasks=items, task=task):
            items.append(task)

    return items


def exists(tasks: list[TaskConfig], task: TaskConfig) -> bool:
    if not isinstance(task, TaskConfig):
        logger.error(f"[DedupError] need type 'TaskConfig' but got type '{type(task)}'")
        return True
    if not tasks:
        return False

    found = False
    for item in tasks:
        left = task.nodes.subscribe_list()
        right = item.nodes.subscribe_list()
        if left:
            if left == right:
                found = True
        else:
            if task.domain == item.domain and task.index == item.index:
                found = True

        if found:
            if not item.rename:
                item.rename = task.rename
            if task.exclude:
                item.exclude = "|".join([item.exclude, task.exclude]).removeprefix("|")
            if task.include:
                item.include = "|".join([item.include, task.include]).removeprefix("|")
            break

    return found


def _subscribe_key(site: SiteConfig) -> str | list[str]:
    subs = site.nodes.subscribe_list()
    if len(subs) <= 1:
        return subs[0] if subs else ""
    return subs


def merge_config(sites: list[SiteConfig]) -> list[SiteConfig]:
    def judge_exists(raw: SiteConfig, target: SiteConfig) -> bool:
        rsubs = raw.nodes.subscribe_list()
        tsubs = target.nodes.subscribe_list()
        rsub = rsubs[0] if rsubs else ""
        if not tsubs:
            if rsub:
                return False
            return utils.trim(raw.domain) == utils.trim(target.domain)
        return rsub in tsubs

    if not sites:
        return []
    items = []
    for site in sites:
        if not isinstance(site, SiteConfig):
            logger.error(f"[MergeError] need type 'SiteConfig' but got type '{type(site)}'")
            continue

        sub = _subscribe_key(site)
        if isinstance(sub, str):
            site.nodes.subscribe = sub

        if isinstance(sub, list) or site.renew:
            items.append(site)
            continue

        found = False
        for item in items:
            found = judge_exists(raw=site, target=item)
            if found:
                if site.errors > item.errors:
                    item.errors = site.errors
                if item.debut:
                    item.debut = site.debut
                if not item.rename:
                    item.rename = site.rename
                if site.exclude:
                    item.exclude = "|".join([item.exclude, site.exclude]).removeprefix("|")
                if site.include:
                    item.include = "|".join([item.include, site.include]).removeprefix("|")
                break
        if not found:
            items.append(site)
    return items


def refresh(
    config: ProcessConfig, push: PushTo, alives: dict[str, bool] | None, filepath: str = "", skip_remark: bool = False
) -> None:
    if not isinstance(config, ProcessConfig) or not isinstance(push, PushTo):
        logger.error("[UpdateError] cannot update remote config because content is empty")
        return

    invalidsubs = None if (skip_remark or not alives) else [k for k, v in alives.items() if not v]
    if invalidsubs and config.crawl:
        crawledsub = config.crawl.persist.subscribe
        threshold = max(config.crawl.max_fails, 1)
        pushconf = config.storage.items.get(crawledsub)
        if push.validate(item=pushconf):
            url = push.raw_url(item=pushconf)
            content = utils.http_get(url=url)
            try:
                data, count = json.loads(content), 0
                for sub in invalidsubs:
                    record = data.pop(sub, None)
                    if not record:
                        continue
                    errors = record.get("errors", 0) + 1
                    count += 1
                    if errors <= threshold and standard_sub(url=sub):
                        record["errors"] = errors
                        data[sub] = record
                if count > 0:
                    content = json.dumps(data)
                    push.push_to(content=content, item=pushconf, group="crawled-remark")
                    logger.info(f"[UpdateInfo] found {count} invalid crawled subscriptions")
            except Exception:
                logger.error("[UpdateError] remark invalid crawled subscriptions failed")

    if not config.update.enable:
        logger.debug("[UpdateError] skip update remote config because enable=[False]")
        return

    if not push.validate(item=config.update.item):
        logger.error("[UpdateError] update config is invalidate")
        return

    sites_conf = merge_config(sites=config.sites)
    if alives:
        sites = []
        for item in sites_conf:
            if not item.enable:
                sites.append(item)
                continue
            sub = _subscribe_key(item)
            source = item.origin
            if (
                source in [Origin.TEMPORARY.name, Origin.OWNED.name]
                or isinstance(sub, list)
                or (isinstance(sub, str) and alives.get(sub, False))
            ):
                item.errors = 0
                item.debut = False
                sites.append(item)
                continue
            expire = Origin.get_expire(source)
            if item.errors < expire and not item.debut:
                item.debut = False
                sites.append(item)
        config.sites = sites
        sites_conf = sites

    if not sites_conf:
        logger.error("[UpdateError] skip update remote config because sites is empty")
        return

    content = json.dumps(config.to_dict())
    if filepath:
        directory = os.path.abspath(os.path.dirname(filepath))
        os.makedirs(directory, exist_ok=True)
        with open(filepath, "w+", encoding="UTF8") as f:
            f.write(content)
            f.flush()

    push.push_to(content=content, item=config.update.item, group="update")


def standard_sub(url: str) -> bool:
    regex = r"https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+(?:(?:(?:/index.php)?/api/v1/client/subscribe\?token=[a-zA-Z0-9]{16,32})|(?:/link/[a-zA-Z0-9]+\?(?:sub|mu|clash)=\d)|(?:/(?:s|sub)/[a-zA-Z0-9]{32}))"
    return re.match(regex, url, flags=re.I) is not None
