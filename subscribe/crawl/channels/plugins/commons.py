# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-11-12

import json

from config.models import NodeInput, StorageItem, TaskParams
from crawl.models import ChannelResult, SubItem
from logger import logger
from origin import Origin
from push import PushTo

from .base import PluginContext


def persist(pushtool: PushTo | None, data: dict[str, object] | None, item: StorageItem | None, meta: str = "") -> None:
    try:
        if (
            data is None
            or not isinstance(data, dict)
            or not isinstance(pushtool, PushTo)
            or not isinstance(item, StorageItem)
            or not pushtool.validate(item=item)
        ):
            logger.debug(f"[{meta}] skip persist subscribes because storage item or data is empty")
            return
        pushtool.push_to(content=json.dumps(data), item=item, group="subscribes")
    except Exception:
        logger.error(f"[{meta}] occur error when persist subscribes")


def as_channel_result(items: list[dict[str, object]] | None) -> ChannelResult:
    result = ChannelResult()
    if not items:
        return result
    urls, uris, proxies = [], [], []
    for item in items:
        if not isinstance(item, dict):
            continue
        subscribe = item.get("subscribe", item.get("sub", ""))
        saved = bool(item.get("saved", False))
        checked = bool(item.get("checked", True))
        origin = item.get("origin", Origin.TEMPORARY.name)
        task = TaskParams(
            push_to=list(item.get("push_to", [])),
            rename=item.get("rename"),
            name=item.get("name"),
            include=item.get("include"),
            exclude=item.get("exclude"),
        )
        links = subscribe if isinstance(subscribe, list) else [subscribe]
        for url in links:
            if not url:
                continue
            urls.append(url)
            result.items.append(
                SubItem(
                    url=url,
                    origin=origin,
                    task=task,
                    name=item.get("name", ""),
                    ready=saved,
                    persist_only=checked and not saved,
                    skip_cache=bool(item.get("skip_cache", item.get("nocache", False))),
                    allow_nonstandard=bool(item.get("allow_nonstandard", item.get("pardon", False))),
                )
            )
        extra = item.get("proxies")
        if extra and isinstance(extra, list):
            if extra and isinstance(extra[0], str):
                uris.extend(extra)
            elif extra and isinstance(extra[0], dict):
                proxies.extend(extra)
    result.nodes = NodeInput(subscribe=list(dict.fromkeys(urls)), uris=list(dict.fromkeys(uris)), proxies=proxies)
    return result


def plugin_params(ctx: PluginContext) -> dict[str, object]:
    if not isinstance(ctx, PluginContext):
        return {}
    params = dict(ctx.params)
    params["task"] = ctx.task
    params["config"] = ctx.task.to_dict()
    if ctx.task.push_to is not None:
        params["config"]["push_to"] = list(ctx.task.push_to)
    return params
