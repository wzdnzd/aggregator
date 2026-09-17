# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, TypeVar

import utils
from config.parse import Node, ObjectNode
from origin import Origin

if TYPE_CHECKING:
    from push import PushTo

TValue = TypeVar("TValue")

CONVERT_TARGETS = [
    "clash",
    "v2ray",
    "singbox",
    "mixed",
    "clashr",
    "quan",
    "quanx",
    "loon",
    "ss",
    "sssub",
    "ssd",
    "ssr",
    "surfboard",
    "surge",
]


def _parse_source_rule(obj: ObjectNode) -> dict[str, object]:
    push_to = obj.string_list("push_to")
    task = TaskParams.parse(obj.field("task"))
    if task.push_to is None:
        task.push_to = list(push_to)
    return {
        "include": obj.regex("include", default=""),
        "exclude": obj.regex("exclude", default=""),
        "push_to": push_to,
        "task": task,
    }


@dataclass
class NodeInput:
    subscribe: str | list[str] = ""
    uris: list[str] = field(default_factory=list)
    proxies: list[dict[str, object]] = field(default_factory=list)

    def empty(self) -> bool:
        subs = self.subscribe if isinstance(self.subscribe, list) else [self.subscribe]
        return (
            not any(utils.trim(str(item)) for item in subs if item is not None) and not self.uris and not self.proxies
        )

    def subscribe_list(self) -> list[str]:
        if isinstance(self.subscribe, list):
            return [utils.trim(item) for item in self.subscribe if utils.trim(item)]
        text = utils.trim(self.subscribe)
        return [text] if text else []


@dataclass
class TaskParams:
    name: str | None = None
    rename: str | None = None
    include: str | None = None
    exclude: str | None = None
    push_to: list[str] | None = None
    check_alive: bool | None = None
    ignore_default_exclude: bool | None = None
    require_tls: bool | None = None
    max_rate: float | None = None
    coupon: str | None = None
    invite_code: str | None = None
    api_prefix: str | None = None
    enable: bool | None = None

    @classmethod
    def parse(cls, node: Node) -> TaskParams:
        if node.absent:
            return cls()
        obj = node.object()
        return cls(
            name=obj.string("name") if obj.has("name") else None,
            rename=obj.string("rename") if obj.has("rename") else None,
            include=obj.regex("include") if obj.has("include") else None,
            exclude=obj.regex("exclude") if obj.has("exclude") else None,
            push_to=obj.string_list("push_to") if obj.has("push_to") else None,
            check_alive=obj.boolean("check_alive"),
            ignore_default_exclude=obj.boolean("ignore_default_exclude"),
            require_tls=obj.boolean("require_tls"),
            max_rate=obj.number("max_rate", minimum=0),
            coupon=obj.string("coupon") if obj.has("coupon") else None,
            invite_code=obj.string("invite_code") if obj.has("invite_code") else None,
            api_prefix=obj.string("api_prefix") if obj.has("api_prefix") else None,
            enable=obj.boolean("enable"),
        )

    def merge(self, override: TaskParams) -> TaskParams:
        def pick(current: TValue, incoming: TValue) -> TValue:
            return incoming if incoming is not None else current

        return TaskParams(
            name=pick(self.name, override.name),
            rename=pick(self.rename, override.rename),
            include=pick(self.include, override.include),
            exclude=pick(self.exclude, override.exclude),
            push_to=pick(self.push_to, override.push_to),
            check_alive=pick(self.check_alive, override.check_alive),
            ignore_default_exclude=pick(self.ignore_default_exclude, override.ignore_default_exclude),
            require_tls=pick(self.require_tls, override.require_tls),
            max_rate=pick(self.max_rate, override.max_rate),
            coupon=pick(self.coupon, override.coupon),
            invite_code=pick(self.invite_code, override.invite_code),
            api_prefix=pick(self.api_prefix, override.api_prefix),
            enable=pick(self.enable, override.enable),
        )

    def apply_to_site(self, site: SiteConfig) -> None:
        if self.name is not None and not site.name:
            site.name = self.name
        if self.rename is not None and not site.rename:
            site.rename = self.rename
        if self.include is not None and not site.include:
            site.include = self.include
        if self.exclude is not None and not site.exclude:
            site.exclude = self.exclude
        if self.push_to is not None and not site.push_to:
            site.push_to = list(self.push_to)
        if self.check_alive is not None and site.check_alive is True:
            site.check_alive = self.check_alive
        if self.ignore_default_exclude is not None:
            site.ignore_default_exclude = self.ignore_default_exclude
        if self.require_tls is not None:
            site.require_tls = self.require_tls
        if self.max_rate is not None:
            site.max_rate = self.max_rate
        if self.coupon is not None and not site.coupon:
            site.coupon = self.coupon
        if self.invite_code is not None and not site.invite_code:
            site.invite_code = self.invite_code
        if self.api_prefix is not None and site.api_prefix == "/api/v1/":
            site.api_prefix = self.api_prefix

    def to_dict(self) -> dict[str, object]:
        payload = {}
        names = (
            "name",
            "rename",
            "include",
            "exclude",
            "push_to",
            "check_alive",
            "ignore_default_exclude",
            "require_tls",
            "max_rate",
            "coupon",
            "invite_code",
            "api_prefix",
            "enable",
        )
        for key in names:
            value = getattr(self, key)
            if value is not None:
                payload[key] = list(value) if key == "push_to" else value
        return payload


@dataclass
class TicketConfig:
    enable: bool = True
    auto_reset: bool = False
    subject: str = ""
    message: str = ""
    level: int = 1

    @classmethod
    def parse(cls, node: Node) -> TicketConfig | None:
        if node.absent:
            return None
        obj = node.object()
        return cls(
            enable=obj.boolean("enable", default=True),
            auto_reset=obj.boolean("auto_reset", default=False),
            subject=obj.string("subject", default="") or "",
            message=obj.string("message", default="") or "",
            level=obj.integer("level", default=1, minimum=1, maximum=3) or 1,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "enable": self.enable,
            "auto_reset": self.auto_reset,
            "subject": self.subject,
            "message": self.message,
            "level": self.level,
        }


@dataclass
class RenewAccount:
    email: str = ""
    password: str = ""
    ticket: TicketConfig | None = None

    @classmethod
    def parse(cls, node: Node) -> RenewAccount:
        obj = node.object()
        return cls(
            email=obj.string("email", default="") or "",
            password=obj.string("password", default="") or "",
            ticket=TicketConfig.parse(obj.field("ticket")),
        )

    def to_dict(self) -> dict[str, object]:
        payload = {"email": self.email, "password": self.password}
        if self.ticket is not None:
            payload["ticket"] = self.ticket.to_dict()
        return payload


@dataclass
class RenewJob:
    account: RenewAccount
    plan_id: int | None = None
    package: str = ""
    method: int | None = None
    coupon_code: str = ""
    api_prefix: str = "/api/v1/"
    enable: bool = True


@dataclass
class RenewConfig:
    accounts: list[RenewAccount] = field(default_factory=list)
    plan_id: int | None = None
    package: str = ""
    method: int | None = None
    coupon_code: str = ""

    @classmethod
    def parse(cls, node: Node) -> RenewConfig | None:
        if node.absent:
            return None
        obj = node.object()
        accounts = []
        if obj.has("accounts"):
            accounts = [RenewAccount.parse(item) for item in obj.field("accounts").array()]
        return cls(
            accounts=accounts,
            plan_id=obj.integer("plan_id"),
            package=obj.string("package", default="") or "",
            method=obj.integer("method"),
            coupon_code=obj.string("coupon_code", default="") or "",
        )

    def jobs(self, coupon: str = "", api_prefix: str = "") -> list[RenewJob]:
        coupon_code = coupon or self.coupon_code
        prefix = api_prefix or "/api/v1/"
        return [
            RenewJob(
                account=account,
                plan_id=self.plan_id,
                package=self.package,
                method=self.method,
                coupon_code=coupon_code,
                api_prefix=prefix,
            )
            for account in self.accounts
        ]

    def to_dict(self) -> dict[str, object]:
        payload = {
            "accounts": [item.to_dict() for item in self.accounts],
            "package": self.package,
            "coupon_code": self.coupon_code,
        }
        if self.plan_id is not None:
            payload["plan_id"] = self.plan_id
        if self.method is not None:
            payload["method"] = self.method
        return payload


@dataclass
class SiteConfig:
    name: str = ""
    enable: bool = True
    domain: str = ""
    nodes: NodeInput = field(default_factory=NodeInput)
    push_to: list[str] = field(default_factory=list)
    rename: str = ""
    include: str = ""
    exclude: str = ""
    ignore_default_exclude: bool = False
    check_alive: bool = True
    max_rate: float = 3.0
    require_tls: bool = False
    skip_captcha: bool = False
    count: int = 1
    coupon: str = ""
    invite_code: str = ""
    api_prefix: str = "/api/v1/"
    origin: str = ""
    errors: int = 0
    debut: bool = False
    renew: RenewConfig | None = None
    skip_cache: bool = False
    allow_nonstandard: bool = False
    persist_only: bool = False
    discovered: bool = False

    @classmethod
    def parse(cls, node: Node) -> SiteConfig:
        obj = node.object()
        return cls(
            name=obj.string("name", default="") or "",
            enable=obj.boolean("enable", default=True),
            domain=obj.string("domain", default="") or "",
            nodes=NodeInput(subscribe=obj.string_or_list("subscribe", default="")),
            push_to=obj.string_list("push_to"),
            rename=obj.string("rename", default="") or "",
            include=obj.regex("include", default=""),
            exclude=obj.regex("exclude", default=""),
            ignore_default_exclude=obj.boolean("ignore_default_exclude", default=False),
            check_alive=obj.boolean("check_alive", default=True),
            max_rate=obj.number("max_rate", default=3.0, minimum=0) or 0,
            require_tls=obj.boolean("require_tls", default=False),
            skip_captcha=obj.boolean("skip_captcha", default=False),
            count=obj.integer("count", default=1, minimum=1, maximum=10) or 1,
            coupon=obj.string("coupon", default="") or "",
            invite_code=obj.string("invite_code", default="") or "",
            api_prefix=obj.string("api_prefix", default="/api/v1/") or "/api/v1/",
            origin=obj.string("origin", default="") or "",
            errors=obj.integer("errors", default=0, minimum=0) or 0,
            debut=obj.boolean("debut", default=False),
            renew=RenewConfig.parse(obj.field("renew")),
        )

    def to_dict(self) -> dict[str, object]:
        payload = {
            "name": self.name,
            "enable": self.enable,
            "domain": self.domain,
            "subscribe": deepcopy(self.nodes.subscribe),
            "push_to": list(self.push_to),
            "rename": self.rename,
            "include": self.include,
            "exclude": self.exclude,
            "ignore_default_exclude": self.ignore_default_exclude,
            "check_alive": self.check_alive,
            "max_rate": self.max_rate,
            "require_tls": self.require_tls,
            "skip_captcha": self.skip_captcha,
            "count": self.count,
            "coupon": self.coupon,
            "invite_code": self.invite_code,
            "api_prefix": self.api_prefix,
            "origin": self.origin,
            "errors": self.errors,
            "debut": self.debut,
        }
        if self.renew is not None:
            payload["renew"] = self.renew.to_dict()
        return payload


@dataclass
class SourceRule:
    include: str = ""
    exclude: str = ""
    push_to: list[str] = field(default_factory=list)
    task: TaskParams = field(default_factory=TaskParams)


@dataclass
class TelegramChannelConfig(SourceRule):
    @classmethod
    def parse(cls, node: Node) -> TelegramChannelConfig:
        obj = node.object()
        return cls(**_parse_source_rule(obj))

    def to_dict(self) -> dict[str, object]:
        payload = {
            "include": self.include,
            "exclude": self.exclude,
            "push_to": list(self.push_to),
        }
        task = self.task.to_dict()
        if task:
            payload["task"] = task
        return payload


@dataclass
class TwitterUserConfig(SourceRule):
    tweets: int = 10
    enable: bool = True

    @classmethod
    def parse(cls, node: Node) -> TwitterUserConfig:
        obj = node.object()
        payload = _parse_source_rule(obj)
        payload["tweets"] = obj.integer("tweets", default=10, minimum=1, maximum=100) or 10
        payload["enable"] = obj.boolean("enable", default=True)
        return cls(**payload)

    def to_dict(self) -> dict[str, object]:
        payload = {
            "enable": self.enable,
            "tweets": self.tweets,
            "include": self.include,
            "exclude": self.exclude,
            "push_to": list(self.push_to),
        }
        task = self.task.to_dict()
        if task:
            payload["task"] = task
        return payload


@dataclass
class PageJob(SourceRule):
    url: str | list[str] = ""
    enable: bool = True
    paged: bool = False
    placeholder: str = ""
    start: int = 1
    end: int = 1
    headers: dict[str, str] | None = None
    origin: str = Origin.PAGE.name
    skip_cache: bool = False

    @classmethod
    def parse(cls, node: Node) -> PageJob:
        obj = node.object()
        payload = _parse_source_rule(obj)
        headers = obj.field("headers").value
        payload.update(
            {
                "url": obj.string_or_list("url", default=""),
                "enable": obj.boolean("enable", default=True),
                "paged": obj.boolean("paged", default=False),
                "placeholder": obj.string("placeholder", default="") or "",
                "start": obj.integer("start", default=1, minimum=0) or 0,
                "end": obj.integer("end", default=1, minimum=0) or 0,
                "headers": headers if isinstance(headers, dict) else None,
                "skip_cache": obj.boolean("skip_cache", default=False),
            }
        )
        return cls(**payload)

    def expand_urls(self) -> list[str]:
        if self.paged:
            if not self.placeholder or not isinstance(self.url, str) or self.placeholder not in self.url:
                return []
            if self.end < self.start:
                return []
            return [self.url.replace(self.placeholder, str(page)) for page in range(self.start, self.end + 1)]
        urls = self.url if isinstance(self.url, list) else [self.url]
        return [utils.trim(str(link)) for link in urls if utils.trim(str(link))]

    def to_dict(self) -> dict[str, object]:
        payload = {
            "enable": self.enable,
            "url": deepcopy(self.url),
            "include": self.include,
            "exclude": self.exclude,
            "push_to": list(self.push_to),
        }
        if self.paged:
            payload["paged"] = True
            payload["placeholder"] = self.placeholder
            payload["start"] = self.start
            payload["end"] = self.end
        if self.skip_cache:
            payload["skip_cache"] = True
        if self.headers:
            payload["headers"] = dict(self.headers)
        task = self.task.to_dict()
        if task:
            payload["task"] = task
        return payload


@dataclass
class GoogleConfig:
    enable: bool = True
    push_to: list[str] = field(default_factory=list)
    exclude: str = ""
    limit: int = 100
    days: int = 7
    exclude_sites: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, node: Node) -> GoogleConfig | None:
        if node.absent:
            return None
        obj = node.object()
        return cls(
            enable=obj.boolean("enable", default=True),
            push_to=obj.string_list("push_to"),
            exclude=obj.regex("exclude", default=""),
            limit=obj.integer("limit", default=100, minimum=1, maximum=1000) or 100,
            days=obj.integer("days", default=7, minimum=1) or 7,
            exclude_sites=obj.string_list("exclude_sites"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "enable": self.enable,
            "push_to": list(self.push_to),
            "exclude": self.exclude,
            "limit": self.limit,
            "days": self.days,
            "exclude_sites": list(self.exclude_sites),
        }


@dataclass
class YandexConfig:
    enable: bool = True
    push_to: list[str] = field(default_factory=list)
    exclude: str = ""
    days: int = 2
    pages: int = 5
    exclude_sites: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, node: Node) -> YandexConfig | None:
        if node.absent:
            return None
        obj = node.object()
        return cls(
            enable=obj.boolean("enable", default=True),
            push_to=obj.string_list("push_to"),
            exclude=obj.regex("exclude", default=""),
            days=obj.integer("days", default=2, minimum=0) or 0,
            pages=obj.integer("pages", default=5, minimum=1) or 5,
            exclude_sites=obj.string_list("exclude_sites"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "enable": self.enable,
            "push_to": list(self.push_to),
            "exclude": self.exclude,
            "days": self.days,
            "pages": self.pages,
            "exclude_sites": list(self.exclude_sites),
        }


@dataclass
class GithubConfig:
    enable: bool = True
    pages: int = 1
    push_to: list[str] = field(default_factory=list)
    exclude: str = ""
    exclude_repos: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, node: Node) -> GithubConfig | None:
        if node.absent:
            return None
        obj = node.object()
        repos = obj.string_list("exclude_repos")
        for index, pattern in enumerate(repos):
            try:
                re.compile(pattern)
            except re.error as exc:
                obj.field("exclude_repos").fail(f"[{index}] is not a valid regex: {exc}")
        return cls(
            enable=obj.boolean("enable", default=True),
            pages=obj.integer("pages", default=1, minimum=1) or 1,
            push_to=obj.string_list("push_to"),
            exclude=obj.regex("exclude", default=""),
            exclude_repos=repos,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "enable": self.enable,
            "pages": self.pages,
            "push_to": list(self.push_to),
            "exclude": self.exclude,
            "exclude_repos": list(self.exclude_repos),
        }


@dataclass
class RepoConfig:
    username: str = ""
    repo: str = ""
    commits: int = 3
    push_to: list[str] = field(default_factory=list)
    exclude: str = ""
    enable: bool = True

    @classmethod
    def parse(cls, node: Node) -> RepoConfig:
        obj = node.object()
        return cls(
            username=obj.string("username", default="") or "",
            repo=obj.string("repo", default="") or "",
            commits=obj.integer("commits", default=3, minimum=1) or 3,
            push_to=obj.string_list("push_to"),
            exclude=obj.regex("exclude", default=""),
            enable=obj.boolean("enable", default=True),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "enable": self.enable,
            "username": self.username,
            "repo": self.repo,
            "commits": self.commits,
            "push_to": list(self.push_to),
            "exclude": self.exclude,
        }


@dataclass
class TelegramConfig:
    enable: bool = True
    pages: int = 1
    exclude: str = ""
    channels: dict[str, TelegramChannelConfig] = field(default_factory=dict)

    @classmethod
    def parse(cls, node: Node) -> TelegramConfig | None:
        if node.absent:
            return None
        obj = node.object()
        channels = {}
        if obj.has("channels"):
            mapping = obj.field("channels").object()
            for name in mapping.keys():
                key = utils.trim(str(name))
                if not key:
                    continue
                channels[key] = TelegramChannelConfig.parse(mapping.field(name))
        return cls(
            enable=obj.boolean("enable", default=True),
            pages=obj.integer("pages", default=1, minimum=1) or 1,
            exclude=obj.regex("exclude", default=""),
            channels=channels,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "enable": self.enable,
            "pages": self.pages,
            "exclude": self.exclude,
            "channels": {name: item.to_dict() for name, item in self.channels.items()},
        }


@dataclass
class TwitterConfig:
    enable: bool = True
    users: dict[str, TwitterUserConfig] = field(default_factory=dict)

    @classmethod
    def parse(cls, node: Node) -> TwitterConfig | None:
        if node.absent:
            return None
        obj = node.object()
        users = {}
        if obj.has("users"):
            mapping = obj.field("users").object()
            for name in mapping.keys():
                key = utils.trim(str(name))
                if not key:
                    continue
                users[key] = TwitterUserConfig.parse(mapping.field(name))
        return cls(enable=obj.boolean("enable", default=True), users=users)

    def to_dict(self) -> dict[str, object]:
        return {
            "enable": self.enable,
            "users": {name: item.to_dict() for name, item in self.users.items()},
        }


@dataclass
class ScriptJob:
    plugin: str
    enable: bool = True
    persist: str | dict[str, str] | None = None
    task: TaskParams = field(default_factory=TaskParams)
    options: dict[str, object] = field(default_factory=dict)

    @classmethod
    def parse(cls, node: Node) -> ScriptJob:
        obj = node.object()
        persist_node = obj.field("persist")
        persist = None
        if not persist_node.absent:
            if isinstance(persist_node.value, str):
                persist = utils.trim(persist_node.value)
            elif isinstance(persist_node.value, dict):
                persist = {}
                for key, value in persist_node.value.items():
                    name = utils.trim(str(key))
                    if not name:
                        continue
                    persist[name] = utils.trim(str(value)) if isinstance(value, str) else value
            else:
                persist_node.fail("must be a string or object")
        return cls(
            plugin=obj.string("plugin", required=True, allow_empty=False),
            enable=obj.boolean("enable", default=True),
            persist=persist,
            task=TaskParams.parse(obj.field("task")),
            options=obj.rest({"plugin", "enable", "persist", "task"}),
        )

    def to_dict(self) -> dict[str, object]:
        payload = {"plugin": self.plugin, "enable": self.enable}
        if self.persist is not None:
            payload["persist"] = deepcopy(self.persist)
        task = self.task.to_dict()
        if task:
            payload["task"] = task
        payload.update(self.options)
        return payload


@dataclass
class RegularizeConfig:
    enable: bool = False
    locate: bool = True
    residential: bool = True
    digits: int = 2
    library: str = ""
    score: bool = False

    @classmethod
    def parse(cls, node: Node) -> RegularizeConfig | None:
        if node.absent:
            return None
        obj = node.object()
        return cls(
            enable=obj.boolean("enable", default=False),
            locate=obj.boolean("locate", default=True),
            residential=obj.boolean("residential", default=True),
            digits=obj.integer("digits", default=2, minimum=1) or 2,
            library=obj.string("library", default="") or "",
            score=obj.boolean("score", default=False),
        )

    def to_dict(self) -> dict[str, object]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass
class GroupConfig:
    name: str
    emoji: bool = True
    list_only: bool = True
    targets: dict[str, str] = field(default_factory=dict)
    regularize: RegularizeConfig | None = None

    @classmethod
    def parse(cls, name: str, node: Node) -> GroupConfig:
        obj = node.object()
        targets = {}
        if obj.has("targets"):
            mapping = obj.field("targets").object()
            for key in mapping.keys():
                category = utils.trim(str(key)).lower()
                if not category:
                    mapping.field(key).fail("contains an empty type")
                if category not in CONVERT_TARGETS:
                    mapping.field(key).fail(f"contains unsupported type: {category}")
                value = mapping.field(key).value
                if not isinstance(value, str) or not utils.trim(value):
                    mapping.field(key).fail("must be a storage item name")
                targets[category] = utils.trim(value)
        if not targets:
            node.fail("should contain at least one conversion target")
        return cls(
            name=name,
            emoji=obj.boolean("emoji", default=True),
            list_only=obj.boolean("list_only", default=True),
            targets=targets,
            regularize=RegularizeConfig.parse(obj.field("regularize")),
        )

    def to_dict(self) -> dict[str, object]:
        payload = {
            "emoji": self.emoji,
            "list_only": self.list_only,
            "targets": dict(self.targets),
        }
        if self.regularize is not None:
            payload["regularize"] = self.regularize.to_dict()
        return payload


@dataclass
class StorageItem:
    username: str = ""
    folder_id: str = ""
    file_id: str = ""
    gist_id: str = ""
    filename: str = ""
    revision: str = ""
    password: str = ""
    expire: int = 0
    local: str = ""

    @classmethod
    def parse(cls, node: Node) -> StorageItem:
        obj = node.object()
        return cls(
            username=obj.string("username", default="") or "",
            folder_id=obj.string("folder_id", default="") or "",
            file_id=obj.string("file_id", default="") or "",
            gist_id=obj.string("gist_id", default="") or "",
            filename=obj.string("filename", default="") or "",
            revision=obj.string("revision", default="") or "",
            password=obj.string("password", default="") or "",
            expire=obj.integer("expire", default=0) or 0,
            local=obj.string("local", default="") or "",
        )

    def to_dict(self) -> dict[str, object]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass
class StorageConfig:
    engine: str = ""
    token: str = ""
    base: str = ""
    domain: str = ""
    items: dict[str, StorageItem] = field(default_factory=dict)

    @classmethod
    def parse(cls, node: Node) -> StorageConfig:
        if node.absent:
            return cls()
        obj = node.object()
        items = {}
        if obj.has("items"):
            mapping = obj.field("items").object()
            for name in mapping.keys():
                key = utils.trim(str(name))
                if not key:
                    continue
                items[key] = StorageItem.parse(mapping.field(name))
        return cls(
            engine=obj.string("engine", default="") or "",
            token=obj.string("token", default="") or "",
            base=obj.string("base", default="") or "",
            domain=obj.string("domain", default="") or "",
            items=items,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "engine": self.engine,
            "token": self.token,
            "base": self.base,
            "domain": self.domain,
            "items": {name: item.to_dict() for name, item in self.items.items()},
        }


@dataclass
class UpdateConfig:
    enable: bool = False
    item: StorageItem | None = None

    @classmethod
    def parse(cls, node: Node) -> UpdateConfig:
        if node.absent:
            return cls()
        obj = node.object()
        item = StorageItem.parse(node)
        filled = any(
            getattr(item, item_field.name) for item_field in fields(StorageItem) if item_field.name != "expire"
        ) or bool(item.expire)
        return cls(enable=obj.boolean("enable", default=False), item=item if filled else None)

    def to_dict(self) -> dict[str, object]:
        payload = {"enable": self.enable}
        if self.item is not None:
            payload.update(self.item.to_dict())
        return payload


@dataclass
class CrawlPersist:
    subscribe: str = ""
    nodes: str = ""

    @classmethod
    def parse(cls, node: Node, storage: StorageConfig) -> CrawlPersist:
        if node.absent:
            return cls()
        obj = node.object()

        def resolve(key: str) -> str:
            name = obj.string(key, default="") or ""
            if name and name not in storage.items:
                obj.field(key).fail(f"storage item not found: {name}")
            return name

        return cls(subscribe=resolve("subscribe"), nodes=resolve("nodes"))

    def to_dict(self) -> dict[str, object]:
        return {"subscribe": self.subscribe, "nodes": self.nodes}


@dataclass
class CrawlConfig:
    enable: bool = True
    exclude: str = ""
    max_fails: int = 5
    include_nodes: bool = True
    persist: CrawlPersist = field(default_factory=CrawlPersist)
    task: TaskParams = field(default_factory=TaskParams)
    google: GoogleConfig | None = None
    yandex: YandexConfig | None = None
    telegram: TelegramConfig | None = None
    twitter: TwitterConfig | None = None
    github: GithubConfig | None = None
    repositories: list[RepoConfig] | None = None
    pages: list[PageJob] | None = None
    scripts: list[ScriptJob] | None = None

    @classmethod
    def parse(cls, node: Node, storage: StorageConfig) -> CrawlConfig | None:
        if node.absent:
            return None
        obj = node.object()
        repositories = None
        if obj.has("repositories"):
            repositories = [RepoConfig.parse(item) for item in obj.field("repositories").array()]
        pages = None
        if obj.has("pages"):
            pages = [PageJob.parse(item) for item in obj.field("pages").array()]
        scripts = None
        if obj.has("scripts"):
            scripts = [ScriptJob.parse(item) for item in obj.field("scripts").array()]
        return cls(
            enable=obj.boolean("enable", default=True),
            exclude=obj.regex("exclude", default=""),
            max_fails=obj.integer("max_fails", default=5, minimum=1) or 5,
            include_nodes=obj.boolean("include_nodes", default=True),
            persist=CrawlPersist.parse(obj.field("persist"), storage),
            task=TaskParams.parse(obj.field("task")),
            google=GoogleConfig.parse(obj.field("google")),
            yandex=YandexConfig.parse(obj.field("yandex")),
            telegram=TelegramConfig.parse(obj.field("telegram")),
            twitter=TwitterConfig.parse(obj.field("twitter")),
            github=GithubConfig.parse(obj.field("github")),
            repositories=repositories,
            pages=pages,
            scripts=scripts,
        )

    def to_dict(self) -> dict[str, object]:
        payload = {
            "enable": self.enable,
            "exclude": self.exclude,
            "max_fails": self.max_fails,
            "include_nodes": self.include_nodes,
            "persist": self.persist.to_dict(),
            "task": self.task.to_dict(),
        }
        if self.google is not None:
            payload["google"] = self.google.to_dict()
        if self.yandex is not None:
            payload["yandex"] = self.yandex.to_dict()
        if self.telegram is not None:
            payload["telegram"] = self.telegram.to_dict()
        if self.twitter is not None:
            payload["twitter"] = self.twitter.to_dict()
        if self.github is not None:
            payload["github"] = self.github.to_dict()
        if self.repositories is not None:
            payload["repositories"] = [item.to_dict() for item in self.repositories]
        if self.pages is not None:
            payload["pages"] = [item.to_dict() for item in self.pages]
        if self.scripts is not None:
            payload["scripts"] = [item.to_dict() for item in self.scripts]
        return payload


@dataclass
class ProcessConfig:
    sites: list[SiteConfig] = field(default_factory=list)
    groups: dict[str, GroupConfig] = field(default_factory=dict)
    storage: StorageConfig = field(default_factory=StorageConfig)
    update: UpdateConfig = field(default_factory=UpdateConfig)
    delay: int = 5000
    crawl: CrawlConfig | None = None

    @classmethod
    def parse(cls, data: dict[str, object]) -> ProcessConfig:
        node = Node(data)
        obj = node.object()
        storage = StorageConfig.parse(obj.field("storage"))
        groups = {}
        if obj.has("groups"):
            mapping = obj.field("groups").object()
            for name in mapping.keys():
                key = utils.trim(str(name))
                if not key:
                    mapping.field(name).fail("contains an empty name")
                groups[key] = GroupConfig.parse(key, mapping.field(name))
        sites = []
        if obj.has("sites"):
            sites = [SiteConfig.parse(item) for item in obj.field("sites").array()]
        return cls(
            sites=sites,
            groups=groups,
            storage=storage,
            update=UpdateConfig.parse(obj.field("update")),
            delay=obj.integer("delay", default=5000, minimum=50) or 5000,
            crawl=CrawlConfig.parse(obj.field("crawl"), storage),
        )

    def verify(self, pushtool: PushTo | None) -> None:
        from push import PushTo as PushTool

        if pushtool is not None and not isinstance(pushtool, PushTool):
            raise ValueError("invalid pushtool")
        items = pushtool.filter_push(self.storage.items) if pushtool else {}
        for name, group in self.groups.items():
            for category, storage_name in group.targets.items():
                if storage_name not in items:
                    raise ValueError(f"missing storage configuration for group {name} to convert type to {category}")

    def to_dict(self) -> dict[str, object]:
        payload = {
            "sites": [site.to_dict() for site in self.sites],
            "groups": {name: group.to_dict() for name, group in self.groups.items()},
            "storage": self.storage.to_dict(),
            "update": self.update.to_dict(),
            "delay": self.delay,
        }
        if self.crawl is not None:
            payload["crawl"] = self.crawl.to_dict()
        return payload
