# -*- coding: utf-8 -*-

from __future__ import annotations

import re
import sys
import urllib.parse

import utils
from config.models import NodeInput, TaskParams
from crawl.models import ChannelResult, SubItem
from logger import logger
from origin import Origin

SUB_REGEX = r"https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+(?::\d+)?(?:(?:(?:/index.php)?/api/v1/client/subscribe\?token=[a-zA-Z0-9]{16,32})|(?:/link/[a-zA-Z0-9]+\?(?:sub|mu|clash)=\d)|(?:/(?:s|sub)/[a-zA-Z0-9]{32}))|https://jmssub\.net/members/getsub\.php\?service=\d+&id=[a-zA-Z0-9\-]{36}(?:\S+)?"
EXTRA_REGEX = r"https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+/sub\?(?:\S+)?target=\S+"
PROTOCOL_REGEX = r"(?:vmess|trojan|ss|ssr|snell|hysteria2|vless|hysteria|tuic|anytls)://[a-zA-Z0-9:.?+=@%&#_\-/]{10,}"


def extract_subscribes(
    content: str,
    push_to: list[str] | None = None,
    include: str = "",
    exclude: str = "",
    limits: int = sys.maxsize,
    source: str = Origin.OWNED.name,
    task: TaskParams | None = None,
    reversed: bool = False,
    skip_cache: bool = False,
    include_nodes: bool = False,
) -> ChannelResult:
    result = ChannelResult()
    if not content:
        return result

    push_to = list(push_to or [])
    task = task or TaskParams(push_to=push_to)
    if task.push_to is None:
        task.push_to = push_to

    try:
        limits = max(1, limits)
        pattern = f"{SUB_REGEX}|{EXTRA_REGEX}"
        if include:
            try:
                pattern = f"{pattern}|{include}" if include.startswith("|") else f"{pattern}|{include}"
                if not include.startswith("|"):
                    pattern = f"{SUB_REGEX}|{EXTRA_REGEX}|{include}"
                else:
                    pattern = f"{SUB_REGEX}|{EXTRA_REGEX}{include}"
                found = re.findall(pattern, content, flags=re.I)
            except Exception:
                logger.error(f"[ExtractError] maybe pattern include exists some problems, include: {include}")
                found = re.findall(f"{SUB_REGEX}|{EXTRA_REGEX}", content)
        else:
            found = re.findall(f"{SUB_REGEX}|{EXTRA_REGEX}", content, flags=re.I)

        try:
            parts = re.findall(
                r"(?m)^#(?:\s+)?(?:!MANAGED-CONFIG|订阅链接)[^\n]*?(https?://[^\s\"'<>]+)",
                content,
                flags=re.I,
            )
            if parts:
                found.extend([utils.trim(item) for item in parts])
        except Exception:
            pass

        if reversed:
            found.reverse()

        seen = []
        uris = []
        for sub in found:
            items = [sub]
            if "url=" in sub:
                query = urllib.parse.urlparse(sub.replace("&amp;", "&")).query
                items = []
                urls = urllib.parse.parse_qs(query).get("url", [])
                if not urls:
                    continue
                for url in urls:
                    if not utils.isurl(url):
                        if include_nodes:
                            uris.extend([x for x in url.split("|") if re.match(PROTOCOL_REGEX, x, flags=re.I)])
                        continue
                    items.extend([x for x in url.split("|") if not re.match(EXTRA_REGEX, x, flags=re.I)])

            for link in items:
                link = re.sub(r"\\/|\/", "/", link, flags=re.I)
                try:
                    if include and not re.match(
                        r"https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+.*",
                        link,
                        flags=re.I,
                    ):
                        continue
                    if exclude and re.search(exclude, link):
                        continue
                except Exception:
                    logger.error(
                        f"[ExtractError] maybe pattern include or exclude exists some problems, include: {include}\texclude: {exclude}"
                    )

                if utils.is_suspicious_url(link):
                    continue
                if link in seen:
                    continue
                seen.append(link)
                result.items.append(
                    SubItem(
                        url=link,
                        origin=source,
                        task=task,
                        skip_cache=skip_cache,
                    )
                )
                if len(seen) >= limits:
                    break
            if len(seen) >= limits:
                break

        if include_nodes:
            try:
                groups = re.findall(PROTOCOL_REGEX, content, flags=re.I)
                if groups:
                    uris.extend([x.lower().strip() for x in groups if x])
            except Exception:
                logger.error("[ExtractError] failed to extract single proxy")

        result.nodes = NodeInput(subscribe=seen, uris=list(dict.fromkeys(uris)))
        return result
    except Exception:
        logger.error("[ExtractError] extract subscribe error")
        return ChannelResult()
