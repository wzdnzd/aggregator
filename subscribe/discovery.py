# -*- coding: utf-8 -*-

from __future__ import annotations

import gzip
import itertools
import json
import random
import re
import socket
import ssl
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

import utils
from airport import AirPort
from logger import logger

DEFAULT_DELIMITER = "@#@#"


@dataclass(frozen=True)
class CollectOptions:
    num_threads: int = 64
    display: bool = True
    persist_path: str = ""
    delimiter: str = ""
    allow_gmail_alias: bool = False
    skip_captcha: bool = False


@dataclass
class AirportRecord:
    domain: str
    coupon: str = ""
    invite_code: str = ""
    api_prefix: str = ""
    source: str = ""

    def to_line(self, delimiter: str, full: bool = False) -> str:
        delimiter = utils.trim(delimiter) or DEFAULT_DELIMITER
        domain = utils.trim(self.domain)
        coupon = utils.trim(self.coupon)
        invite_code = utils.trim(self.invite_code)
        api_prefix = utils.trim(self.api_prefix)
        if full:
            return f"{domain}\t{delimiter}\t{coupon}\t{delimiter}\t{invite_code}\t{delimiter}\t{api_prefix}"
        if coupon:
            return f"{domain}\t{delimiter}\t{coupon}"
        return domain

    @classmethod
    def from_line(cls, line: str, delimiter: str) -> AirportRecord | None:
        text = utils.trim(line)
        if not text or text.startswith("#"):
            return None

        delimiter = utils.trim(delimiter) or DEFAULT_DELIMITER
        parts = text.rsplit(delimiter, maxsplit=3)
        domain = utils.trim(parts[0])
        if not domain:
            return None

        return cls(
            domain=domain,
            coupon=utils.trim(parts[1]) if len(parts) > 1 else "",
            invite_code=utils.trim(parts[2]) if len(parts) > 2 else "",
            api_prefix=utils.trim(parts[3]) if len(parts) > 3 else "",
        )


def parse_records(content: str, delimiter: str) -> dict[str, AirportRecord]:
    if not content or not isinstance(content, str):
        logger.warning("cannot found any domain due to content is empty or not string")
        return {}

    records: dict[str, AirportRecord] = {}
    for line in content.split("\n"):
        record = AirportRecord.from_line(line, delimiter)
        if record:
            records[record.domain] = record
    return records


def save_records(
    records: dict[str, AirportRecord],
    filepath: str,
    delimiter: str,
    full: bool = False,
) -> None:
    if not records or not isinstance(records, dict):
        return

    filepath = utils.trim(filepath)
    if not filepath:
        return

    delimiter = utils.trim(delimiter) or DEFAULT_DELIMITER
    lines = [record.to_line(delimiter, full=full) for record in records.values() if record and record.domain]
    utils.write_file(filename=filepath, lines=lines)


def count_telegram_pages(channel: str) -> int:
    if not channel or channel.strip() == "":
        return 0

    url = f"https://t.me/s/{channel}"
    content = utils.http_get(url=url)
    cursor = 0
    try:
        pattern = rf'<link\s+rel="canonical"\s+href="/s/{channel}\?before=(\d+)">'
        groups = re.findall(pattern, content)
        cursor = int(groups[0]) if groups else cursor
    except Exception:
        logger.error(f"[CrawlError] cannot count page num, channel: {channel}")

    return cursor


def extract_telegram_sites(url: str) -> list[str]:
    if not url:
        return []

    logger.info(f"[AirPortCrawl] start collect airport, url: {url}")

    content = utils.http_get(url=url)
    if not content:
        logger.error(f"[CrawlError] cannot any content from url: {url}")
        return []
    try:
        pattern = r'href="(https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+/?)"\s+target="_blank"\s+rel="noopener">'
        groups = re.findall(pattern, content)
        return list(set(groups)) if groups else []
    except Exception:
        return []


def follow_redirect(url: str, retry: int = 3) -> str:
    if not url or retry <= 0:
        return ""

    headers = {
        "User-Agent": utils.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    try:
        request = urllib.request.Request(url=url, headers=headers, method="GET")
        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
        return response.geturl()
    except Exception:
        time.sleep(random.randint(1, 3))
        return follow_redirect(url=url, retry=retry - 1)


def extract_listing(url: str, separator: str, address_regex: str, coupon_regex: str) -> dict[str, str]:
    url = utils.trim(url)
    content = utils.http_get(url=url)
    if not content:
        return {}

    mapping: dict[str, str] = {}
    try:
        groups = re.split(utils.trim(separator), content, flags=re.M)
        if not groups:
            logger.warning(f"[AirPortCollector] cannot found any domains from [{url}]")
            return {}

        for group in groups:
            if not group or not isinstance(group, str):
                continue

            words = re.findall(utils.trim(address_regex), group, flags=re.M)
            address = words[0] if words else ""
            if not address:
                continue

            words = re.findall(utils.trim(coupon_regex), group, flags=re.M)
            coupon = words[0] if words else ""
            domain = utils.extract_domain(url=address, include_protocal=True)
            mapping[domain] = coupon
    except Exception:
        logger.error(f"[AirPortCollector] occur error when crawl from [{url}], message: \n{traceback.format_exc()}")

    logger.info(f"[AirPortCollector] finished crawl from [{url}], found {len(mapping)} domains")
    return mapping


def extract_links(url: str, prefix: str, pattern: str) -> list[str]:
    content = utils.http_get(url=url)
    groups = re.findall(pattern, content, flags=re.I)
    if not groups:
        logger.warning(f"[AirPortCollector] cannot fetch article from url: {url}")
        return []

    prefix = utils.trim(prefix)
    return list(set([urllib.parse.urljoin(prefix, item) for item in groups if item]))


class AirportSource(ABC):
    name: str = ""
    persist: bool = True

    @abstractmethod
    def crawl(self, options: CollectOptions) -> list[AirportRecord]:
        raise NotImplementedError

    def to_records(self, mapping: dict[str, str] | None) -> list[AirportRecord]:
        records: list[AirportRecord] = []
        for domain, coupon in (mapping or {}).items():
            domain = utils.trim(domain)
            if not domain:
                continue
            records.append(AirportRecord(domain=domain, coupon=utils.trim(coupon), source=self.name))
        return records


class RegexAirportSource(AirportSource):
    url: str = ""
    separator: str = ""
    address_regex: str = ""
    coupon_regex: str = ""

    def crawl(self, options: CollectOptions) -> list[AirportRecord]:
        return self.to_records(
            extract_listing(
                url=self.url,
                separator=self.separator,
                address_regex=self.address_regex,
                coupon_regex=self.coupon_regex,
            )
        )


class MaomengSource(RegexAirportSource):
    name = "maomeng"
    url = "https://maomeng.xyz/2021/06/11/ji-chang-tui-jian-chang-qi-geng-xin"
    separator = r'<h3 id="[^\r\n]+"><a href="#[^\r\n]+"'
    address_regex = r"<p>官网：<a[^\r\n]+href=\"(https?://[^\s]+)\">.*</a></p>"
    coupon_regex = r"<p>[^<]*(?:优惠|白嫖)码：<code>([^<]+)</code></p>"


class AskahhSource(RegexAirportSource):
    name = "askahh"
    url = "https://www.askahh.com/archives/17"
    separator = r"<h2[^>]*>[^<]+</h2>"
    address_regex = r'<a class="no-external-link" href="(https?://[^"]+)" target="_blank">'
    coupon_regex = r"使用优惠码\s*(?:<strong>)?([^<]+?)(?:</strong>)?\s*免费购买"


class TelegramSource(AirportSource):
    name = "telegram"
    persist = False

    def __init__(self, channel: str, page_num: int) -> None:
        self.channel = utils.trim(channel)
        self.page_num = page_num

    def crawl(self, options: CollectOptions) -> list[AirportRecord]:
        urls = self._page_urls()
        if not urls:
            return []

        if len(urls) == 1:
            sites = extract_telegram_sites(urls[0])
        else:
            batches = utils.multi_thread_run(func=extract_telegram_sites, tasks=urls)
            sites = list(itertools.chain.from_iterable(batch or [] for batch in batches))

        records: list[AirportRecord] = []
        seen: set[str] = set()
        for site in sites:
            domain = utils.extract_domain(site, True)
            if not domain or domain in seen:
                continue
            seen.add(domain)
            records.append(AirportRecord(domain=domain, source=self.name))
        return records

    def _page_urls(self) -> list[str]:
        if not self.channel:
            return []

        page_num = max(self.page_num, 1)
        url = f"https://t.me/s/{self.channel}"
        if page_num == 1:
            return [url]

        cursor = count_telegram_pages(self.channel)
        if cursor == 0:
            return []

        pages = range(cursor, -1, -20)
        page_num = min(page_num, len(pages))
        logger.info(f"[TelegramCrawl] starting crawl from telegram, channel: {self.channel}, pages: {page_num}")
        return [f"{url}?before={item}" for item in pages[:page_num]]


class HwanzSource(AirportSource):
    name = "hwanz"
    url = "https://raw.githubusercontent.com/hwanz/SSR-V2ray-Trojan-vpn/main/README.md"

    def crawl(self, options: CollectOptions) -> list[AirportRecord]:
        content = utils.http_get(url=self.url)
        groups = re.findall(r"\[.*\]\((https?:\/\/[^\s\r\n]+)\)[^\r\n]+\d+G.*", content, flags=re.I)
        if not groups:
            return []

        try:
            links = [utils.trim(item).lower() for item in groups if item]
            mapping = {utils.extract_domain(url=item, include_protocal=True): "" for item in links if item}
            logger.info(f"[AirPortCollector] finished crawl from [{self.url}], found {len(mapping)} domains")
            return self.to_records(mapping)
        except Exception:
            logger.error(
                f"[AirPortCollector] occur error when crawl from [{self.url}], message: \n{traceback.format_exc()}"
            )
            return []


class CcbaoheSource(AirportSource):
    name = "ccbaohe"
    url = "https://ccbaohe.com/jcjd.html"

    def crawl(self, options: CollectOptions) -> list[AirportRecord]:
        content = utils.http_get(url=self.url)
        mapping: dict[str, str] = {}
        try:
            groups = re.split(r"【[^【]*】", content, flags=re.M)
            if not groups:
                logger.warning(f"[AirPortCollector] cannot found any domains from [{self.url}]")
                return []

            candidates: dict[str, str] = {}
            for group in groups:
                if not group:
                    continue

                for text in re.split(r"<br\s*/?>\s*<br\s*/?>", group, flags=re.I):
                    words = re.findall(r'注册地址：<a href="(https?://[^"\s]+)"', text, flags=re.M)
                    address = words[0] if words else ""
                    if not address:
                        continue

                    words = re.findall(
                        r"(?:白嫖码|优惠码|折码)[:\s：]+(?:<[^>]+>\s*)*([A-Za-z0-9_\-]+)", text, flags=re.M
                    )
                    candidates[address] = words[0] if words else ""

            urls = list(candidates.keys())
            redirected = utils.multi_thread_run(
                func=follow_redirect,
                tasks=urls,
                num_threads=options.num_threads,
            )

            for index, original in enumerate(urls):
                domain = utils.extract_domain(url=redirected[index], include_protocal=True)
                if not domain:
                    continue
                mapping[domain] = candidates.get(original, "")
        except Exception:
            logger.error(
                f"[AirPortCollector] occur error when crawl from [{self.url}], message: \n{traceback.format_exc()}"
            )

        logger.info(f"[AirPortCollector] finished crawl from [{self.url}], found {len(mapping)} domains")
        return self.to_records(mapping)


class YgpySource(AirportSource):
    name = "ygpy"
    base_url = "https://ygpy.net"
    index_urls = ("/vpn/free.html", "/vpn/free")

    def crawl(self, options: CollectOptions) -> list[AirportRecord]:
        pages = self._monthly_pages()
        if not pages:
            logger.warning(f"[AirPortCollector] cannot get article from url: {self.base_url}")
            return []

        separator = r'<h2 id="id-\d+" tabindex="-1">'
        address_regex = r'<li>网站：<a href="(https?://[^"]+)"'
        coupon_regex = r"使用优惠[码券]\s*(?:<code>)?([^\s<]+)(?:</code>)?\s*0\s*元购买"

        tasks = [[page, separator, address_regex, coupon_regex] for page in pages]
        listings = utils.multi_thread_run(func=extract_listing, tasks=tasks)

        mapping: dict[str, str] = {}
        for listing in listings:
            if listing and isinstance(listing, dict):
                mapping.update(listing)

        return self.to_records(self._drop_non_sites(mapping))

    def _drop_non_sites(self, mapping: dict[str, str]) -> dict[str, str]:
        skipped = {
            "t.me",
            "www.t.me",
            "telegram.me",
            "telegram.org",
            "ygpy.net",
            "www.ygpy.net",
            "ygpy.org",
            "www.ygpy.org",
        }
        cleaned: dict[str, str] = {}
        for domain, coupon in mapping.items():
            host = utils.extract_domain(domain, include_protocal=False).lower()
            if not host or host in skipped:
                continue
            cleaned[domain] = coupon
        return cleaned

    def _monthly_pages(self) -> list[str]:
        paths: list[str] = []
        for suffix in self.index_urls:
            content = utils.http_get(url=f"{self.base_url}{suffix}")
            if not content:
                continue
            found = re.findall(r"/vpn/test/\d{4}/\d{2}\.html", content)
            if found:
                paths = found
                break

        pages: list[str] = []
        seen: set[str] = set()
        for path in sorted(paths):
            if path in seen:
                continue
            seen.add(path)
            pages.append(urllib.parse.urljoin(self.base_url, path))
        return pages


@dataclass
class ProbeResult:
    blocked: bool = False
    backend: str = ""


class BackendResolver:
    def resolve(self, domain: str, retry: int = 2) -> str:
        # TODO: exploring a more generalized approach to backend addresses
        attempts = max(retry, 1)
        for probe in (self._probe_env, self._probe_zero_theme, self._probe_buddy, self._probe_aurora):
            result = probe(domain, attempts)
            if result.blocked:
                return ""
            if result.backend:
                return result.backend
        return domain

    def _fetch_path(self, domain: str, suffix: str, retry: int) -> tuple[bool, str]:
        count, suffix = 0, utils.trim(suffix)
        url = urllib.parse.urljoin(domain, suffix)

        while count < retry:
            count += 1
            try:
                request = urllib.request.Request(url=url, headers=utils.DEFAULT_HTTP_HEADERS, method="GET")
                response = urllib.request.urlopen(request, timeout=6, context=utils.CTX)

                word = "" if not suffix else (suffix if suffix.startswith("/") else "/" + suffix)
                if word and not utils.trim(response.geturl()).endswith(word):
                    return True, ""

                content = response.read()
                try:
                    content = str(content, encoding="utf8")
                except Exception:
                    content = gzip.decompress(content).decode("utf8")

                return False, content
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return False, ""
            except urllib.error.URLError as exc:
                if isinstance(exc.reason, (socket.gaierror, ssl.SSLError, socket.timeout)):
                    return True, ""
            except Exception:
                pass

        return False, ""

    def _probe_env(self, domain: str, retry: int) -> ProbeResult:
        blocked, content = self._fetch_path(domain, suffix="/env.js", retry=retry)
        if blocked:
            return ProbeResult(blocked=True)
        if not content:
            return ProbeResult()

        groups = re.findall(r"\bhost\b:(?:\s+)?[\"\'](https?://[^\s\r\t]+)[\"\']", content, flags=re.I)
        if groups:
            return ProbeResult(backend=utils.trim(groups[0]))

        groups = re.findall(r"window.routerBase(?:\s+)?=(?:\s+)?['\"](https?://.*)['\"]", content, flags=re.I)
        backend = groups[0].rstrip("/") if groups and groups[0] else ""
        return ProbeResult(backend=backend)

    def _probe_zero_theme(self, domain: str, retry: int) -> ProbeResult:
        # for https://github.com/amyouran/v2board-Zero-Theme
        blocked, content = self._fetch_path(domain, suffix="/config.json", retry=retry)
        if blocked:
            return ProbeResult(blocked=True)
        if not content:
            return ProbeResult()

        try:
            data = json.loads(content)
            link = utils.trim(data.get("api_base", ""))
            if not link:
                # for https://github.com/DyAxy/V2B-Theme-Nest
                link = utils.trim(data.get("apiUrl", ""))
            return ProbeResult(backend=utils.extract_domain(url=link, include_protocal=True))
        except Exception:
            return ProbeResult()

    def _probe_buddy(self, domain: str, retry: int) -> ProbeResult:
        # for https://github.com/vlesstop/v2board-theme-buddy
        blocked, content = self._fetch_path(domain, suffix="/config.js", retry=retry)
        if blocked:
            return ProbeResult(blocked=True)

        groups = re.findall(r"\bhost\b:(?:\s+)?[\"\'](https?://[^\s\r\t]+)[\"\']", content, flags=re.I)
        return ProbeResult(backend="" if not groups else utils.trim(groups[0]))

    def _probe_aurora(self, domain: str, retry: int) -> ProbeResult:
        # for https://github.com/krsunm/Aurora
        blocked, content = self._fetch_path(domain, suffix="", retry=retry)
        if blocked:
            return ProbeResult(blocked=True)

        groups = re.findall(r"\bserverUrl\b:(?:\s+)?[\"\'](https?://[^\s\r\t]+)[\"\']", content, flags=re.I)
        return ProbeResult(backend="" if not groups else utils.trim(groups[0]))


class DomainValidator:
    def validate(self, url: str, allow_gmail_alias: bool = False, skip_captcha: bool = False) -> tuple[bool, str]:
        try:
            if not url:
                return False, ""

            requirement = AirPort.get_register_require(domain=url)
            blocked = (
                requirement.invite
                or (skip_captcha and requirement.recaptcha)
                or (
                    requirement.whitelist
                    and requirement.verify
                    and (not allow_gmail_alias or "gmail.com" not in requirement.whitelist)
                )
            )
            return not blocked, requirement.api_prefix
        except Exception:
            return False, ""


class AirportCollector:
    def __init__(
        self,
        sources: Sequence[AirportSource],
        options: CollectOptions,
        resolver: BackendResolver | None = None,
        validator: DomainValidator | None = None,
    ) -> None:
        self.sources = list(sources)
        self.options = options
        self.resolver = resolver or BackendResolver()
        self.validator = validator or DomainValidator()

    @classmethod
    def default(cls, channel: str, page_num: int, options: CollectOptions) -> AirportCollector:
        return cls(sources=default_sources(channel, page_num), options=options)

    def collect(self) -> dict[str, AirportRecord]:
        discovered, persisted = self._discover()
        self._persist(persisted)
        resolved = self._resolve(discovered)
        return self._validate(resolved)

    def _discover(self) -> tuple[dict[str, AirportRecord], dict[str, AirportRecord]]:
        discovered: dict[str, AirportRecord] = {}
        persisted: dict[str, AirportRecord] = {}
        for source in self.sources:
            items = source.crawl(self.options) or []
            for record in items:
                domain = utils.trim(record.domain)
                if not domain:
                    continue
                record.domain = domain
                if not record.source:
                    record.source = source.name
                discovered[domain] = record
                if source.persist:
                    persisted[domain] = record
        return discovered, persisted

    def _persist(self, records: dict[str, AirportRecord]) -> None:
        save_records(
            records=records,
            filepath=self.options.persist_path,
            delimiter=self.options.delimiter,
            full=False,
        )

    def _resolve(self, records: dict[str, AirportRecord]) -> list[AirportRecord]:
        domains = list(records.keys())
        logger.info(f"[AirPortCollector] fetched {len(domains)} airport, start extracting real routing addresses")
        backends = utils.multi_thread_run(
            func=self.resolver.resolve,
            tasks=domains,
            num_threads=self.options.num_threads,
            show_progress=self.options.display,
        )

        resolved: list[AirportRecord] = []
        for index, backend in enumerate(backends):
            if not backend:
                continue
            origin = records.get(domains[index])
            if origin is None:
                continue
            resolved.append(
                AirportRecord(
                    domain=backend,
                    coupon=origin.coupon,
                    invite_code=origin.invite_code,
                    source=origin.source,
                )
            )
        return resolved

    def _validate(self, records: list[AirportRecord]) -> dict[str, AirportRecord]:
        logger.info("[AirPortCollector] extract real base url finished, start to check it now")
        tasks = [[record.domain, self.options.allow_gmail_alias, self.options.skip_captcha] for record in records]
        results = utils.multi_thread_run(
            func=self.validator.validate,
            tasks=tasks,
            num_threads=self.options.num_threads,
            show_progress=self.options.display,
        )

        available: dict[str, AirportRecord] = {}
        for index, record in enumerate(records):
            accepted, api_prefix = results[index]
            if not accepted:
                continue
            record.api_prefix = api_prefix or ""
            available[record.domain] = record

        logger.info(f"[AirPortCollector] finished collect airport, availables: {len(available)}")
        return available


def default_sources(channel: str, page_num: int) -> list[AirportSource]:
    return [
        TelegramSource(channel=channel, page_num=page_num),
        HwanzSource(),
        CcbaoheSource(),
        MaomengSource(),
        AskahhSource(),
        YgpySource(),
    ]


def collect_airport(
    channel: str,
    page_num: int,
    num_threads: int = 64,
    display: bool = True,
    filepath: str = "",
    delimiter: str = "",
    allow_gmail_alias: bool = False,
    skip_captcha: bool = False,
) -> dict[str, AirportRecord]:
    options = CollectOptions(
        num_threads=num_threads,
        display=display,
        persist_path=filepath,
        delimiter=delimiter,
        allow_gmail_alias=allow_gmail_alias,
        skip_captcha=skip_captcha,
    )
    return AirportCollector.default(channel=channel, page_num=page_num, options=options).collect()
