# -*- coding: utf-8 -*-

from __future__ import annotations

import base64
import re

import push
import utils
from config.models import (
    CrawlConfig,
    NodeInput,
    SiteConfig,
    StorageConfig,
    StorageItem,
    TaskParams,
)
from crawl.channels import CHANNELS
from crawl.helpers import check_status, load_records, naming_task, save_records
from crawl.models import ChannelResult, CrawlContext, SubItem
from logger import logger
from origin import Origin
from push import PushTo
from workflow import standard_sub


def _site_from_item(item: SubItem, shared: TaskParams) -> SiteConfig:
    task = shared.merge(item.task) if item.task else shared
    site = SiteConfig(
        name=item.name or naming_task(item.url),
        nodes=NodeInput(subscribe=item.url),
        push_to=list(task.push_to or []),
        rename=task.rename or "",
        include=task.include or "",
        exclude=task.exclude or "",
        ignore_default_exclude=bool(task.ignore_default_exclude) if task.ignore_default_exclude is not None else False,
        check_alive=True if task.check_alive is None else task.check_alive,
        max_rate=task.max_rate if task.max_rate is not None else 3.0,
        require_tls=bool(task.require_tls),
        origin=item.origin or Origin.TEMPORARY.name,
        errors=item.errors,
        debut=True if item.debut or item.ready else False,
        skip_cache=item.skip_cache,
        allow_nonstandard=item.allow_nonstandard,
        persist_only=item.persist_only,
        discovered=item.discovered or item.ready,
    )
    return site


def _site_from_nodes(name: str, nodes: NodeInput, origin: str, task: TaskParams) -> SiteConfig:
    return SiteConfig(
        name=name or origin.lower(),
        nodes=NodeInput(subscribe=list(nodes.subscribe_list()), uris=list(nodes.uris), proxies=list(nodes.proxies)),
        push_to=list(task.push_to or []),
        rename=task.rename or "",
        include=task.include or "",
        exclude=task.exclude or "",
        ignore_default_exclude=bool(task.ignore_default_exclude) if task.ignore_default_exclude is not None else False,
        check_alive=True if task.check_alive is None else task.check_alive,
        max_rate=task.max_rate if task.max_rate is not None else 3.0,
        require_tls=bool(task.require_tls),
        origin=origin,
        debut=True,
    )


def _usable_subscribe(url: str, exclude: str = "") -> bool:
    url = utils.trim(url)
    if not url:
        return False
    if utils.is_suspicious_url(url):
        return False
    exclude = utils.trim(exclude)
    if exclude:
        try:
            if re.search(exclude, url):
                return False
        except Exception:
            pass
    return True


def _collapse_items(items: list[SubItem] | None) -> list[SubItem]:
    merged: dict[str, SubItem] = {}
    for item in items or []:
        url = utils.trim(item.url)
        if not url:
            continue
        item.url = url
        current = merged.get(url)
        if current is None:
            merged[url] = item
            continue
        winner, loser = current, item
        if item.ready and not current.ready:
            winner, loser = item, current
        elif (not item.persist_only) and current.persist_only and item.ready == current.ready:
            winner, loser = item, current
        winner.errors = max(winner.errors, loser.errors)
        winner.allow_nonstandard = winner.allow_nonstandard or loser.allow_nonstandard
        winner.skip_cache = winner.skip_cache or loser.skip_cache
        if loser.discovered:
            winner.discovered = True
        merged[url] = winner
    return list(merged.values())


def _unpack_status(mask: object) -> tuple[bool, bool]:
    if isinstance(mask, tuple) and len(mask) >= 2:
        return bool(mask[0]), bool(mask[1])
    return False, False


def run(
    config: CrawlConfig,
    storage: StorageConfig | None = None,
    num_threads: int = 50,
    display: bool = True,
    mode: int = 0,
) -> list[SiteConfig]:
    mode = 0 if not isinstance(mode, int) else min(max(mode, 0), 2)
    if not isinstance(config, CrawlConfig) or not config.enable:
        return []

    pushtool = None
    try:
        if isinstance(storage, StorageConfig):
            pushtool = push.get_instance(storage)
    except Exception:
        pushtool = None

    persist_subscribe = storage.items.get(config.persist.subscribe) if storage and config.persist.subscribe else None
    persist_nodes = storage.items.get(config.persist.nodes) if storage and config.persist.nodes else None
    if mode == 1 and not (pushtool and persist_subscribe):
        logger.warning(
            "[CrawlWarn] skip crawling tasks because the mode is set to crawl only but no valid persistence configuration is set"
        )
        return []

    ctx = CrawlContext(
        mode=mode,
        include_nodes=config.include_nodes,
        max_fails=config.max_fails,
        exclude=config.exclude,
        task=config.task,
        storage=storage,
        pushtool=pushtool,
        num_threads=num_threads,
        display=display,
    )

    result = ChannelResult()
    if mode != 2:
        sections = [
            ("google", config.google),
            ("yandex", config.yandex),
            ("telegram", config.telegram),
            ("twitter", config.twitter),
            ("github", config.github),
            ("repositories", config.repositories),
            ("pages", config.pages),
            ("scripts", config.scripts),
        ]
        for name, section in sections:
            if section is None:
                continue
            if getattr(section, "enable", True) is False:
                continue
            channel = CHANNELS.get(name)
            if channel is None:
                continue
            try:
                result.merge(channel.crawl(section, ctx))
            except Exception as exc:
                logger.error(f"[CrawlError] crawl channel {name} failed: {exc}")

    sites: list[SiteConfig] = []
    cached: dict[str, dict[str, object]] = {}
    if pushtool and persist_subscribe:
        cached = load_records(pushtool, persist_subscribe) or {}

    result.items = _collapse_items(result.items)
    known = {item.url for item in result.items if item.url}
    for item in result.items:
        meta = cached.get(item.url)
        if not isinstance(meta, dict) or item.ready:
            continue
        item.errors = max(item.errors, int(meta.get("errors", 0) or 0))

    stale_keys: list[str] = []
    for raw_url, meta in cached.items():
        url = utils.trim(raw_url)
        if not url or not isinstance(meta, dict):
            stale_keys.append(raw_url)
            continue
        if url in known:
            continue
        if not _usable_subscribe(url, config.exclude):
            stale_keys.append(raw_url)
            continue
        result.add_subscribe(
            url,
            meta.get("origin", Origin.TEMPORARY.name),
            TaskParams(push_to=list(meta.get("push_to", []))),
            skip_cache=bool(meta.get("skip_cache", False)),
            allow_nonstandard=bool(meta.get("allow_nonstandard", False)),
            errors=int(meta.get("errors", 0) or 0),
            discovered=True,
            debut=bool(meta.get("debut", False)),
        )
        known.add(url)
    for key in stale_keys:
        cached.pop(key, None)

    pending: list[SubItem] = []
    seen: set[str] = set()
    for item in result.items:
        url = utils.trim(item.url)
        if not url or url in seen:
            continue
        if not _usable_subscribe(url, config.exclude):
            continue
        seen.add(url)
        item.url = url
        site = _site_from_item(item, config.task)
        if item.persist_only:
            cached[item.url] = _cache_record(site)
            continue
        if item.ready:
            cached[item.url] = _cache_record(site)
            sites.append(site)
            continue
        pending.append(item)

    if pending:
        logger.info(f"[CrawlInfo] start to validate {len(pending)} subscriptions")
        masks = utils.multi_thread_run(
            func=check_status,
            tasks=[[item.url, 2, 5, 12, 72] for item in pending],
            num_threads=ctx.num_threads,
            show_progress=ctx.display,
        )
        for item, mask in zip(pending, masks):
            available, expired = _unpack_status(mask)
            site = _site_from_item(item, config.task)
            if not available:
                errors = int(cached.get(item.url, {}).get("errors", item.errors) or 0) + 1
                site.errors = errors
                if errors > config.max_fails or expired:
                    continue
                if not item.allow_nonstandard and not standard_sub(item.url) and mode != 1:
                    continue
                cached[item.url] = _cache_record(site)
                continue
            site.errors = 0
            site.debut = True
            cached[item.url] = _cache_record(site)
            sites.append(site)

    extra = NodeInput(uris=list(result.nodes.uris), proxies=list(result.nodes.proxies))
    if not config.include_nodes:
        extra.uris = []
    if not extra.empty():
        sites.append(_site_from_nodes("crawled-nodes", extra, Origin.TEMPORARY.name, config.task))
        _snapshot_nodes(pushtool, persist_nodes, extra)

    if pushtool and persist_subscribe and cached:
        survivors = {key: value for key, value in cached.items() if not value.get("skip_cache")}
        if survivors:
            save_records(pushtool, persist_subscribe, survivors)

    if mode == 1:
        logger.warning("[CrawlWarn] skip aggregate because mode=1 represents only crawling subscriptions")

    logger.info(f"[CrawlInfo] crawl finished, found {len(sites)} sites")
    return sites


def _cache_record(site: SiteConfig) -> dict[str, object]:
    return {
        "origin": site.origin,
        "push_to": site.push_to,
        "errors": site.errors,
        "discovered": True,
        "skip_cache": site.skip_cache,
        "allow_nonstandard": site.allow_nonstandard,
        "debut": site.debut,
    }


def _snapshot_nodes(pushtool: PushTo | None, item: StorageItem | None, extra: NodeInput) -> None:
    if not isinstance(pushtool, PushTo) or not isinstance(item, StorageItem):
        return
    try:
        if extra.uris:
            content = base64.b64encode("\n".join(extra.uris).encode()).decode()
        elif extra.proxies:
            import yaml

            content = yaml.dump({"proxies": extra.proxies}, allow_unicode=True)
        else:
            return
        pushtool.push_to(content=content, item=item, group="proxies")
    except Exception:
        logger.error("[CrawlError] persist crawled nodes failed")
