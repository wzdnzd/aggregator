# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import json
import os
import re
from dataclasses import dataclass

import renewal
import utils
from airport import ANOTHER_API_PREFIX, AirPort
from logger import logger
from origin import Origin
from push import PushTo


@dataclass
class TaskConfig:
    # 任务名
    name: str

    # subconverter程序名
    bin_name: str

    # 任务编号
    taskid: int = -1

    # 网址域名
    domain: str = ""

    # 订阅地址
    sub: str = ""

    # 任务编号
    index: int = 1

    # 失败重试次数
    retry: int = 3

    # 最高允许倍率
    rate: float = 20.0

    # 标签
    tag: str = ""

    # 套餐续期配置
    renew: dict = None

    # 优惠码
    coupon: str = ""

    # 节点重命名规则
    rename: str = ""

    # 节点排除规则
    exclude: str = ""
    include: str = ""

    # ChatGPT连通性测试节点过滤规则
    chatgpt: dict = None

    # 是否检测节点存活状态
    liveness: bool = True

    # 是否强制开启 tls 及阻止跳过证书验证
    disable_insecure: bool = False

    # 覆盖subconverter默认exclude规则
    ignorede: bool = False

    # 是否允许特殊协议
    special_protocols: bool = False

    # 对于具有邮箱域名白名单且需要验证码的情况，是否使用 Gmail 别名邮箱尝试，为 True 时表示不使用
    rigid: bool = True

    # 是否丢弃可能需要人机验证的站点
    chuck: bool = False

    # 邀请码
    invite_code: str = ""

    # 接口地址前缀，如 /api/v1/ 或 /api?scheme=
    api_prefix: str = "/api/v1/"


def execute(task_conf: TaskConfig) -> list:
    if not task_conf or not isinstance(task_conf, TaskConfig):
        return []

    obj = AirPort(
        name=task_conf.name,
        site=task_conf.domain,
        sub=task_conf.sub,
        rename=task_conf.rename,
        exclude=task_conf.exclude,
        include=task_conf.include,
        liveness=task_conf.liveness,
        coupon=task_conf.coupon,
        api_prefix=task_conf.api_prefix,
    )

    logger.info(f"start fetch proxy: name=[{task_conf.name}]\tid=[{task_conf.index}]\tdomain=[{obj.ref}]")

    # 套餐续期
    if task_conf.renew:
        sub_url = renewal.add_traffic_flow(
            domain=obj.ref,
            params=task_conf.renew,
            jsonify=obj.api_prefix == ANOTHER_API_PREFIX,
        )
        if sub_url and not obj.registed:
            obj.registed = True
            obj.sub = sub_url

    cookie, authorization = obj.get_subscribe(
        retry=task_conf.retry,
        rigid=task_conf.rigid,
        chuck=task_conf.chuck,
        invite_code=task_conf.invite_code,
    )

    proxies = obj.parse(
        cookie=cookie,
        auth=authorization,
        retry=task_conf.retry,
        rate=task_conf.rate,
        bin_name=task_conf.bin_name,
        tag=task_conf.tag,
        disable_insecure=task_conf.disable_insecure,
        ignore_exclude=task_conf.ignorede,
        chatgpt=task_conf.chatgpt,
        special_protocols=task_conf.special_protocols,
    )

    logger.info(
        f"finished fetch proxy: name=[{task_conf.name}]\tid=[{task_conf.index}]\tdomain=[{obj.ref}]\tcount=[{len(proxies)}]"
    )

    return proxies


def executewrapper(task_conf: TaskConfig) -> tuple[int, list]:
    if not task_conf:
        return (-1, [])

    taskid = task_conf.taskid
    proxies = execute(task_conf=task_conf)
    return (taskid, proxies)


def liveness_fillter(proxies: list) -> tuple[list, list]:
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
            p.pop("chatgpt", False)
            nochecks.append(p)

    return checks, nochecks


def cleanup(filepath: str = "", filenames: list = []) -> None:
    if not filepath or not filenames:
        return

    for name in filenames:
        filename = os.path.join(filepath, name)
        if os.path.exists(filename):
            os.remove(filename)


def dedup_task(tasks: list) -> list:
    if not tasks:
        return []
    items = []
    for task in tasks:
        if not exists(tasks=items, task=task):
            items.append(task)

    return items


def exists(tasks: list, task: TaskConfig) -> bool:
    if not isinstance(task, TaskConfig):
        logger.error(f"[DedupError] need type 'TaskConfig' but got type '{type(task)}'")
        return True
    if not tasks:
        return False

    found = False
    for item in tasks:
        if task.sub != "":
            if task.sub == item.sub:
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


def merge_config(configs: list) -> list:
    def judge_exists(raw: dict, target: dict) -> bool:
        if not raw or not target:
            return False

        rsub = raw.get("sub").strip()
        tsub = target.get("sub", "")
        if not tsub:
            if rsub:
                return False
            return raw.get("domain", "").strip() == target.get("domain", "").strip()
        if isinstance(tsub, str):
            return rsub == tsub.strip()
        for sub in tsub:
            if rsub == sub.strip():
                return True
        return False

    if not configs:
        return []
    items = []
    for conf in configs:
        if not isinstance(conf, dict):
            logger.error(f"[MergeError] need type 'dict' but got type '{type(conf)}'")
            continue

        sub = conf.get("sub", "")
        if isinstance(sub, list) and len(sub) <= 1:
            sub = sub[0] if sub else ""

        # 人工维护配置，无需合并
        if isinstance(sub, list) or conf.get("renew", {}):
            items.append(conf)
            continue

        found = False
        conf["sub"] = sub
        for item in items:
            found = judge_exists(raw=conf, target=item)
            if found:
                if conf.get("errors", 0) > item.get("errors", 0):
                    item["errors"] = conf.get("errors", 0)
                if item.get("debut", False):
                    item["debut"] = conf.get("debut", False)
                if not item.get("rename", ""):
                    item["rename"] = conf.get("rename", "")
                if conf.get("exclude", ""):
                    item["exclude"] = "|".join([item.get("exclude", ""), conf.get("exclude", "")]).removeprefix("|")
                if conf.get("include", ""):
                    item["include"] = "|".join([item.get("include", ""), conf.get("include", "")]).removeprefix("|")

                break

        if not found:
            items.append(conf)

    return items


def refresh(config: dict, push: PushTo, alives: dict, filepath: str = "", skip_remark: bool = False) -> None:
    if not config or not push:
        logger.error("[UpdateError] cannot update remote config because content is empty")
        return

    # mark invalid crawled subscription
    invalidsubs = None if (skip_remark or not alives) else [k for k, v in alives.items() if not v]
    if invalidsubs:
        crawledsub = config.get("crawl", {}).get("persist", {}).get("subs", "")
        threshold = max(config.get("threshold", 1), 1)
        pushconf = config.get("groups", {}).get(crawledsub, {})
        if push.validate(push_conf=pushconf):
            url = push.raw_url(push_conf=pushconf)
            content = utils.http_get(url=url)
            try:
                data, count = json.loads(content), 0
                for sub in invalidsubs:
                    record = data.pop(sub, None)
                    if not record:
                        continue

                    defeat = record.get("defeat", 0) + 1
                    count += 1
                    if defeat <= threshold and standard_sub(url=sub):
                        record["defeat"] = defeat
                        data[sub] = record

                if count > 0:
                    content = json.dumps(data)
                    push.push_to(content=content, push_conf=pushconf, group="crawled-remark")
                    logger.info(f"[UpdateInfo] found {count} invalid crawled subscriptions")
            except:
                logger.error(f"[UpdateError] remark invalid crawled subscriptions failed")

    update_conf = config.get("update", {})
    if not update_conf.get("enable", False):
        logger.debug("[UpdateError] skip update remote config because enable=[False]")
        return

    if not push.validate(push_conf=update_conf):
        logger.error(f"[UpdateError] update config is invalidate")
        return

    domains = merge_config(configs=config.get("domains", []))
    if alives:
        sites = []
        for item in domains:
            source = item.get("origin", "")
            sub = item.get("sub", "")
            if isinstance(sub, list) and len(sub) <= 1:
                sub = sub[0] if sub else ""
            if source in [Origin.TEMPORARY.name, Origin.OWNED.name] or isinstance(sub, list) or alives.get(sub, False):
                item.pop("errors", None)
                item.pop("debut", None)
                sites.append(item)
                continue

            errors = item.get("errors", 1)
            expire = Origin.get_expire(source)
            if errors < expire and not item.get("debut", False):
                item.pop("debut", None)
                sites.append(item)

        config["domains"] = sites
        domains = config.get("domains", [])

    if not domains:
        logger.error("[UpdateError] skip update remote config because domians is empty")
        return

    content = json.dumps(config)
    if filepath:
        directory = os.path.abspath(os.path.dirname(filepath))
        os.makedirs(directory, exist_ok=True)
        with open(filepath, "w+", encoding="UTF8") as f:
            f.write(content)
            f.flush()

    push.push_to(content=content, push_conf=update_conf, group="update")


def standard_sub(url: str) -> bool:
    regex = r"https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+(?:(?:(?:/index.php)?/api/v1/client/subscribe\?token=[a-zA-Z0-9]{16,32})|(?:/link/[a-zA-Z0-9]+\?(?:sub|mu|clash)=\d))"
    return re.match(regex, url, flags=re.I) is not None
