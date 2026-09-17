# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-08-13

import base64
import gzip
import json
import random
import re
import time
import urllib
import urllib.request

import utils
from config.models import StorageItem
from crawl.models import ChannelResult
from logger import logger
from push import PushTo

from . import commons
from .base import PluginContext, ScriptPlugin, register_plugin
from .commons import as_channel_result, plugin_params


def fetch(email: str, retry: int = 2) -> str:
    if retry <= 0:
        return ""

    params = {"email": email, "action": "getrss"}
    url = "https://appls.eu.org/getrss.php"
    data = urllib.parse.urlencode(params).encode(encoding="UTF8")
    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": "https://www.v2rayfree.eu.org",
        "referer": "https://www.v2rayfree.eu.org/",
        "user-agent": utils.USER_AGENT,
    }

    try:
        request = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
        if response.getcode() == 200:
            content = response.read()
            try:
                content = gzip.decompress(content).decode("utf8")
            except:
                content = str(content, encoding="utf8")

            fake_email, index = email, email.find("@")
            if index != -1:
                fake_email = email[: index // 2] + "***" + email[index:]

            if "已封禁" in content:
                logger.warning(f"[GetRSSError] {content}, email=[{fake_email}]")
                return ""

            regex = "https://f\.kxyz\.eu\.org/f\.php\?r=([A-Za-z0-9/=]+)"
            groups = re.findall(regex, content)
            if not groups:
                return ""

            subscribe = str(base64.b64decode(groups[0]), encoding="UTF8")
            return subscribe

    except:
        time.sleep(random.random())
        return fetch(email, retry - 1)


def getrss(params: dict[str, object], ctx: PluginContext | None = None) -> list[dict[str, object]]:
    if not params or type(params) != dict:
        return []

    emails = params.get("emails", [])
    if emails and type(emails) == list:
        emails = [x for x in emails if re.match(r"^\w+([-+.]\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*$", x)]

    config = params.get("config", {})
    if not emails or not config or type(config) != dict or not config.get("push_to"):
        logger.error(f"[V2RayFreeError] cannot fetch subscribes bcause missing some parameters")
        return []

    include = str(params.get("include", "") or "").strip()
    if ctx is not None and not isinstance(ctx, PluginContext):
        return []
    pushtool = ctx.pushtool if ctx else None
    persist = ctx.persist if ctx else None
    exists = load(pushtool=pushtool, persist=persist)
    emails = [x for x in emails if x not in exists.keys()]

    results, subscribes = utils.multi_thread_run(func=fetch, tasks=emails), []
    exists.update(filter(data=dict(zip(emails, results))))

    # persist subscribes
    commons.persist(pushtool=pushtool, data=exists, item=persist)

    results = list(exists.values())
    results.extend(config.get("sub", []))

    for item in set(results):
        if not item or (include and not re.search(include, item, re.I)):
            if item:
                logger.info(f"[V2RayFreeInfo] subscribe: {item} has been filtered")

            continue

        subscribes.append(item)

    if not subscribes:
        logger.info(f"[V2RayFreeInfo] getrss finished, cannot found any subscribes")
        return []

    config["sub"] = subscribes
    config["name"] = "okgg" if not config.get("name", "") else config.get("name", "")
    config["push_to"] = list(set(config["push_to"]))
    config["saved"] = True

    logger.info(f"[V2RayFreeInfo] getrss finished, found {len(subscribes)} subscribes")
    return [config]


def load(pushtool: PushTo | None, persist: StorageItem | None) -> dict[str, object]:
    if not isinstance(pushtool, PushTo) or not isinstance(persist, StorageItem) or not pushtool.validate(item=persist):
        return {}

    url = pushtool.raw_url(item=persist)
    try:
        content = utils.http_get(url=url)
        data = json.loads(content)
        return filter(data=data)
    except:
        return {}


def filter(data: dict[str, object]) -> dict[str, object]:
    if not data or type(data) != dict:
        return {}

    emails, subscribes = list(data.keys()), list(data.values())
    usables = utils.multi_thread_run(func=check, tasks=subscribes)
    for i in range(len(usables)):
        if not usables[i]:
            data.pop(emails[i], "")

    return data


def check(subscribe: str) -> bool:
    if not subscribe:
        return False

    content = utils.http_get(url=subscribe)
    return (
        re.match(
            "^([A-Za-z0-9+/]{4})*([A-Za-z0-9+/]{4}|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{2}==)$",
            content,
            re.I,
        )
        is not None
    )


class V2RayFreePlugin(ScriptPlugin[dict[str, object]]):
    name = "v2rayfree"

    def parse(self, ctx: PluginContext) -> dict[str, object]:
        return plugin_params(ctx)

    def run(self, config: dict[str, object], ctx: PluginContext) -> ChannelResult:
        return as_channel_result(getrss(config, ctx))


register_plugin(V2RayFreePlugin())
