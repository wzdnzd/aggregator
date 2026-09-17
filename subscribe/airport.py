# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import base64
import concurrent.futures
import json
import os
import random
import re
import string
import time
import traceback
import urllib
import urllib.parse
import urllib.request
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from http.client import HTTPMessage, HTTPResponse
from urllib.request import Request

import mailtm
import renewal
import utils
import yaml
from config.models import NodeInput
from logger import logger
from outbound import verify

import subconverter
from clash import is_mihomo

EMAILS_DOMAINS = [
    "gmail.com",
    "outlook.com",
    "163.com",
    "126.com",
    "sina.com",
    "hotmail.com",
    "qq.com",
    "foxmail.com",
    "hotmail.com",
    "yahoo.com",
]

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

# 重命名分隔符
RENAME_SEPARATOR = "#@&#@"

# 重命名正则表达式组分隔符
RENAME_GROUP_SEPARATOR = "`"

# 生成随机字符串时候选字符
LETTERS = set(string.ascii_letters + string.digits)

# 常见非标准 API 前缀
ANOTHER_API_PREFIX = "/api?scheme="

# 标记数字位数
# SUFFIX_BITS = 2


class Category(Enum):
    # 远程订阅
    HTTP = 1

    # 本地文件
    FILE = 2

    # 单个节点链接
    LINK = 3


# deal with !<str>
def str_constructor(loader: yaml.Loader, node: yaml.Node) -> str:
    return str(loader.construct_scalar(node))


yaml.SafeLoader.add_constructor("str", str_constructor)
yaml.FullLoader.add_constructor("str", str_constructor)

_UNQUOTED_IPV6 = re.compile(
    r"(?im)(?P<pre>(?:^|[\s,{])(?:server|ip|ipv6)\s*:\s*)" r'(?P<val>(?![\'"])\S*:\S*)' r"(?P<post>\s*(?:,|\}|$|\n|#))"
)


def quote_unquoted_ipv6(document: str) -> str:
    if not document:
        return ""

    def replacer(match: re.Match[str]) -> str:
        return f'{match.group("pre")}"{match.group("val")}"{match.group("post")}'

    return _UNQUOTED_IPV6.sub(replacer, document)


def lookup(name: str) -> Category:
    name = utils.trim(name)
    for item in Category:
        if item.name.lower() == name.lower():
            return item

    return Category.HTTP


@dataclass
class RegisterRequire:
    # 是否需要验证邮箱
    verify: bool

    # 是否需要邀请码
    invite: bool

    # 是否包含验证码
    recaptcha: bool

    # 邮箱域名白名单
    whitelist: list = field(default_factory=list)

    # 是否是 sspanel 面板
    sspanel: bool = False

    # 接口地址前缀
    api_prefix: str = ""


class NoRedirHandler(urllib.request.HTTPRedirectHandler):
    def http_error_302(self, req: Request, fp: HTTPResponse, code: int, msg: str, headers: HTTPMessage) -> HTTPResponse:
        return fp

    http_error_301 = http_error_302


def issspanel(domain: str) -> bool:
    def sniff(url: str) -> int:
        if utils.isblank(url):
            return -1

        try:
            opener = urllib.request.build_opener(NoRedirHandler)
            opener.addheaders = [("User-Agent", utils.USER_AGENT)]
            response = opener.open(fullurl=url, timeout=10)
            return response.getcode()
        except Exception:
            return -2

    return (
        False
        if (
            sniff(url=f"{domain}/api/v1/passport/auth/login") == 200
            or sniff(url=f"{domain}/api?scheme=passport/auth/login") == 200
        )
        else sniff(url=f"{domain}/auth/login") == 200
    )


class AirPort:
    def __init__(
        self,
        name: str,
        site: str,
        nodes: NodeInput | None = None,
        rename: str = "",
        exclude: str = "",
        include: str = "",
        check_alive: bool = True,
        coupon: str = "",
        api_prefix: str = "/api/v1/",
    ) -> None:
        if site.endswith("/"):
            site = site[: len(site) - 1]

        self.api_prefix = utils.get_subpath(api_prefix)
        self.nodes = nodes if isinstance(nodes, NodeInput) else NodeInput()
        subs = self.nodes.subscribe_list()
        sub = subs[0] if subs else ""
        if sub:
            if sub.startswith(utils.FILEPATH_PROTOCAL):
                ref = sub[8:]
            else:
                ref = utils.extract_domain(sub, include_protocal=True)

            self.fetch = ""
            self.ref = ref
            self.reg = ""
            self.registed = True
            self.send_email = ""
        else:
            self.fetch = f"{site}{self.api_prefix}user/server/fetch"
            self.registed = False
            self.send_email = f"{site}{self.api_prefix}passport/comm/sendEmailVerify"
            self.reg = f"{site}{self.api_prefix}passport/auth/register"
            self.ref = site
        self.name = name
        self.rename = rename
        self.exclude = exclude
        self.include = include
        self.check_alive = check_alive
        self.coupon = "" if utils.isblank(coupon) else coupon
        self.headers = {
            "User-Agent": utils.USER_AGENT,
            "Referer": self.ref + "/",
            "Origin": self.ref,
            "Host": utils.extract_domain(self.ref),
        }
        self.username = ""
        self.password = ""
        self.available = True

    @staticmethod
    def get_register_require(
        domain: str,
        proxy: str = "",
        default: bool = True,
        api_prefix: str = "",
    ) -> RegisterRequire:
        domain = utils.extract_domain(url=domain, include_protocal=True)
        if not domain:
            return RegisterRequire(verify=default, invite=default, recaptcha=default)

        api_prefix = utils.trim(api_prefix)
        subpath = utils.get_subpath(api_prefix)

        content = utils.http_get(
            url=f"{domain}{subpath}guest/comm/config",
            retry=2,
            proxy=proxy,
        )
        if not content and (not api_prefix or subpath != ANOTHER_API_PREFIX):
            api_prefix = ANOTHER_API_PREFIX

            logger.debug(f"[QueryError] try to explore another register require, domain: {domain}")
            content = utils.http_get(url=f"{domain}{api_prefix}guest/comm/config", retry=2, proxy=proxy)

        if not content.startswith("{") and content.endswith("}"):
            logger.debug(f"[QueryError] cannot get register require, domain: {domain}")
            return RegisterRequire(verify=default, invite=default, recaptcha=default)

        try:
            data = json.loads(content).get("data", {})
            need_verify = data.get("is_email_verify", 0) != 0
            invite_force = data.get("is_invite_force", 0) != 0
            recaptcha = data.get("is_recaptcha", 0) != 0
            whitelist = data.get("email_whitelist_suffix", [])

            try:
                from collections.abc import Iterable
            except ImportError:
                from collections import Iterable

            if whitelist is None or not isinstance(whitelist, Iterable):
                whitelist = []

            return RegisterRequire(
                verify=need_verify,
                invite=invite_force,
                recaptcha=recaptcha,
                whitelist=whitelist,
                api_prefix=api_prefix,
            )

        except:
            return RegisterRequire(verify=default, invite=default, recaptcha=default)

    def sen_email_verify(self, email: str, retry: int = 3) -> bool:
        if not email.strip() or retry <= 0:
            return False
        params = {"email": email.strip()}

        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        headers = deepcopy(self.headers)

        headers["Content-Type"] = "application/x-www-form-urlencoded"
        if self.api_prefix == ANOTHER_API_PREFIX:
            headers["Content-Type"] = "application/json"
            data = json.dumps(params).encode(encoding="UTF8")

        try:
            request = urllib.request.Request(self.send_email, data=data, headers=headers, method="POST")
            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            if not response or response.getcode() != 200:
                return False

            return json.loads(response.read()).get("data", False)
        except:
            return self.sen_email_verify(email=email, retry=retry - 1)

    def register(
        self, email: str, password: str, email_code: str = None, invite_code: str = None, retry: int = 3
    ) -> tuple[str, str]:
        if retry <= 0:
            logger.info(f"achieved max retry when register, domain: {self.ref}")
            return "", ""

        if not password:
            password = utils.random_chars(random.randint(8, 16), punctuation=True)

        params = {
            "email": email,
            "password": password,
            "invite_code": utils.trim(invite_code),
            "email_code": utils.trim(email_code),
        }

        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        headers = deepcopy(self.headers)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        if self.api_prefix == ANOTHER_API_PREFIX:
            headers["Content-Type"] = "application/json"
            data = json.dumps(params).encode(encoding="UTF8")

        try:
            request = urllib.request.Request(self.reg, data=data, headers=headers, method="POST")
            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            code = 400 if not response else response.getcode()
            if code != 200:
                logger.error(f"[RegisterError] request error when register, domain: {self.ref}, code={code}")
                return "", ""

            self.username = email
            self.password = password

            cookies = utils.extract_cookie(response.getheader("Set-Cookie"))
            data = json.loads(response.read()).get("data", {})
            token, authorization = "", ""
            if isinstance(data, dict):
                token = data.get("token", "")
                authorization = data.get("auth_data", "")

            # 先判断是否存在免费套餐，如果存在则购买
            self.order_plan(
                email=email,
                password=password,
                cookies=cookies,
                authorization=authorization,
            )

            subscribe_info = renewal.get_subscribe_info(
                domain=self.ref,
                cookies=cookies,
                authorization=authorization,
                api_prefix=self.api_prefix,
            )
            if subscribe_info:
                self.nodes.subscribe = subscribe_info.sub_url
            if not self.nodes.subscribe_list():
                if token:
                    self.nodes.subscribe = f"{self.ref}/api/v1/client/subscribe?token={token}"
                else:
                    logger.error(f"[RegisterError] cannot get token when register, domain: {self.ref}")

            return cookies, authorization
        except:
            return self.register(email, password, email_code, invite_code, retry - 1)

    def order_plan(
        self,
        email: str,
        password: str,
        cookies: str = "",
        authorization: str = "",
        retry: int = 3,
    ) -> bool:
        jsonify = self.api_prefix == ANOTHER_API_PREFIX
        plan = renewal.get_free_plan(
            domain=self.ref,
            cookies=cookies,
            authorization=authorization,
            retry=retry,
            coupon=self.coupon,
            api_prefix=self.api_prefix,
            jsonify=jsonify,
        )

        if not plan:
            logger.info(f"not exists free plan, domain: {self.ref}")
            return False
        else:
            logger.info(f"found free plan, domain: {self.ref}, plan: {plan}")

        methods = renewal.get_payment_method(
            domain=self.ref,
            cookies=cookies,
            authorization=authorization,
            api_prefix=self.api_prefix,
        )

        method = random.choice(methods) if methods else 1
        params = {
            "email": email,
            "passwd": password,
            "package": plan.package,
            "plan_id": plan.plan_id,
            "method": method,
            "coupon_code": self.coupon,
            "api_prefix": self.api_prefix,
            "jsonify": jsonify,
        }

        success = renewal.flow(
            domain=self.ref,
            params=params,
            reset=False,
            cookies=cookies,
            authorization=authorization,
        )

        if success and (plan.renew or plan.reset):
            logger.info(f"[RegisterSuccess] register successed, domain: {self.ref}")

        return success

    def fetch_unused(self, cookies: str, auth: str = "", rate: float = 3.0) -> list[dict[str, object]]:
        if (not cookies and not auth) or "" == self.fetch.strip():
            return []

        if cookies:
            self.headers["Cookie"] = cookies.strip()
        if auth:
            self.headers["authorization"] = auth.strip()
        try:
            proxies = []
            request = urllib.request.Request(self.fetch, headers=self.headers)
            response = urllib.request.urlopen(request, timeout=5, context=utils.CTX)
            if response.getcode() != 200:
                return proxies

            datas = json.loads(response.read())["data"]
            for item in datas:
                if float(item.get("rate", "1.0")) > rate:
                    proxies.append(item.get("name"))

            return proxies
        except:
            return []

    def get_subscribe(
        self,
        retry: int,
        rr: RegisterRequire = None,
        allow_gmail_alias: bool = False,
        skip_captcha: bool = False,
        invite_code: str = None,
    ) -> tuple[str, str]:
        if self.registed:
            return "", ""

        invite_code = utils.trim(invite_code)
        rr = (
            rr
            if rr is not None
            else self.get_register_require(
                domain=self.ref,
                default=False,
                api_prefix=self.api_prefix,
            )
        )

        # 需要邀请码或者强制验证
        if (
            (rr.invite and not invite_code)
            or (skip_captcha and rr.recaptcha)
            or (rr.whitelist and rr.verify and (not allow_gmail_alias or "gmail.com" not in rr.whitelist))
        ):
            self.available = False
            return "", ""

        # API地址前缀
        self.api_prefix = rr.api_prefix or self.api_prefix

        if not rr.verify:
            email = utils.random_chars(length=random.randint(6, 10), punctuation=False)
            password = utils.random_chars(length=random.randint(8, 16), punctuation=True)

            email_suffixs = rr.whitelist if rr.whitelist else EMAILS_DOMAINS
            email_domain = random.choice(email_suffixs)
            if not email_domain:
                return "", ""

            email = f"{email}@{email_domain}"
            return self.register(email=email, password=password, invite_code=invite_code, retry=retry)
        else:
            only_gmail = True if rr.whitelist and rr.verify else False

            try:
                mailbox = mailtm.create_instance(only_gmail=only_gmail)
                account = mailbox.get_account()
                if not account:
                    logger.error(f"cannot create temporary email account, site: {self.ref}")
                    return "", ""

                message = None
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    starttime = time.time()
                    try:
                        future = executor.submit(mailbox.monitor_account, account, 120, random.randint(1, 3))
                        success = self.sen_email_verify(email=account.address, retry=3)
                        if not success:
                            executor.shutdown(wait=False)
                            return "", ""
                        message = future.result(timeout=120)
                        logger.debug(
                            f"email has been received, domain: {self.ref}\tcost: {int(time.time()- starttime)}s"
                        )
                    except concurrent.futures.TimeoutError:
                        logger.error(
                            f"receiving mail timeout, site: {self.ref}, address: {mailbox.api_address}, email: {account.address}"
                        )

                if not message:
                    return "", ""

                # 如果标准正则无法提取验证码则直接匹配数字
                mask = mailbox.extract_mask(message.text) or mailbox.extract_mask(message.text, r"[：\s]+([0-9]{6})")
                mailbox.delete_account(account=account)
                if not mask:
                    logger.error(f"cannot fetch mask, url: {self.ref}, message: {message.text}")
                    return "", ""

                return self.register(
                    email=account.address,
                    password=account.password,
                    email_code=mask,
                    invite_code=invite_code,
                    retry=retry,
                )
            except:
                return "", ""

    def _fetch_text(self, url: str, retry: int) -> str:
        url = utils.trim(url)
        if not url:
            return ""
        if url.startswith(utils.FILEPATH_PROTOCAL):
            file = url[len(utils.FILEPATH_PROTOCAL) :]
            if not os.path.exists(file) or not os.path.isfile(file):
                logger.error(f"[ParseError] file: {file} not found")
                return ""
            with open(file, "r", encoding="utf8") as reader:
                return reader.read()

        client = f"{utils.USER_AGENT}; Clash.Meta; Mihomo; Shadowrocket;"
        headers = {"User-Agent": client}
        trace = os.environ.get("TRACE_ENABLE", "false").lower() in ["true", "1"]
        return utils.http_get(
            url=url,
            headers=headers,
            retry=retry,
            timeout=120,
            trace=trace,
            interval=1,
            max_size=15 * 1024 * 1024,
        ).strip()

    def parse(
        self,
        cookie: str,
        auth: str,
        retry: int,
        rate: float,
        bin_name: str,
        require_tls: bool = False,
        udp: bool = True,
        ignore_exclude: bool = False,
        special_protocols: bool = False,
        nodes: NodeInput | None = None,
    ) -> list[dict[str, object]]:
        source = nodes if isinstance(nodes, NodeInput) else self.nodes
        collected = []
        chars = utils.random_chars(length=3, punctuation=False)
        artifact = f"{self.name}-{chars}"

        for url in source.subscribe_list():
            text = self._fetch_text(url, retry)
            if not text or (
                text.startswith("{") and text.endswith("}") and not re.search(r'"outbounds":', text, flags=re.I)
            ):
                logger.error(f"[ParseError] cannot found any proxies, subscribe: {utils.mask(url=url)}")
                continue
            collected.extend(
                self.decode(
                    text=text,
                    artifact=f"{artifact}-sub",
                    program=bin_name,
                    ignore=ignore_exclude,
                    special=special_protocols,
                    do_verify=False,
                )
            )

        if source.uris:
            collected.extend(
                self.decode(
                    text="\n".join(source.uris),
                    artifact=f"{artifact}-uri",
                    program=bin_name,
                    ignore=ignore_exclude,
                    special=special_protocols,
                    do_verify=False,
                )
            )

        collected.extend([item for item in source.proxies if isinstance(item, dict)])
        if not collected:
            if source.empty():
                logger.error(f"[ParseError] cannot found any proxies because node input is empty, domain: {self.ref}")
            return []

        parsed = [item for item in collected if verify(item, special_protocols)]
        if not parsed:
            logger.info(f"cannot found any proxy, domain: {self.ref}")
            return []

        proxies = []
        unused_nodes = self.fetch_unused(cookie, auth, rate) if cookie or auth else []
        subscribe_url = source.subscribe_list()[0] if source.subscribe_list() else ""
        for item in parsed:
            name = item.get("name", "")
            if utils.isblank(name) or name in unused_nodes:
                continue

            if re.match(r"^JMS-\d+@[a-zA-Z0-9.]+:\d+$", name, flags=re.I):
                server = name.split("@", maxsplit=1)[1]
                hostname = utils.trim(server.split(":", maxsplit=1)[0]).lower()
                if re.match(r"^(\d+\.){3}\d+$", item.get("server", ""), flags=re.I):
                    item["server"] = hostname

            try:
                if self.include and not re.search(self.include, name, re.I):
                    continue
                if self.exclude and re.search(self.exclude, name, re.I):
                    continue
            except Exception:
                logger.error(
                    f"filter proxies error, maybe include or exclude regex exists problems, include: {self.include}\texclude: {self.exclude}"
                )

            try:
                if self.rename:
                    pattern_groups = self.rename.split(RENAME_GROUP_SEPARATOR)
                    for group in pattern_groups:
                        rename_regex = utils.trim(group)
                        if not rename_regex:
                            continue
                        if RENAME_SEPARATOR in rename_regex:
                            words = rename_regex.split(RENAME_SEPARATOR, maxsplit=1)
                            old = words[0].strip()
                            new = words[1].strip()
                            if old:
                                name = re.sub(old, new, name, flags=re.I)
                        else:
                            name = re.sub(rename_regex, "", name, flags=re.I)

                regex = r"(?:https?://)?(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z\u4e00-\u9fa5]{2,}"
                name = re.sub(regex, "", name, flags=re.I)
            except Exception:
                logger.error(
                    f"rename error, name: {name},\trename: {self.rename}\tseparator: {RENAME_SEPARATOR}\tdomain: {self.ref}"
                )

            name = re.sub(
                r"\[[^\[]*\]|[（\(][^（\(]*[\)）]|{[^{]*}|<[^<]*>|【[^【]*】|「[^「]*」|[^a-zA-Z0-9\u4e00-\u9fa5_×\.\-|\s]",
                " ",
                name,
                flags=re.I,
            ).strip()

            name = (
                re.sub(r"\s+|\r|\n|\\r|\\n", " ", name, flags=re.I)
                .replace("_", "-")
                .replace("+", "-")
                .strip(r"""!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~ """)
            )
            name = re.sub(r"((\s+)?-(\s+)?)+", "-", name)
            if not name:
                name = f"{self.name[0]}{self.name[-1]}-{''.join(random.sample(string.ascii_uppercase, 3))}"

            if len(name) > 30:
                i, j, k, n = 10, 4, 4, len(name)
                alphabets = [x for x in name[i : n - j] if x in LETTERS]
                if len(alphabets) > k:
                    abbreviation = "".join(random.sample(alphabets, k)).strip()
                else:
                    abbreviation = "".join(alphabets)
                name = f"{name[:i].strip()}-{abbreviation}-{name[-j:].strip()}"

            name = re.sub(r"\s+(\d+)[\s_\-\|]+([A-Za-z])\b", r"-\1\2", name)
            item["name"] = re.sub(r"(-\d+[A-Za-z])+$", "", name).upper()
            item["sub"] = subscribe_url
            item["liveness"] = self.check_alive

            if require_tls:
                if "skip-cert-verify" in item:
                    item["skip-cert-verify"] = False
                if "tls" in item:
                    item["tls"] = True

            if udp and "udp" not in item and (item.get("type", "") != "snell" or int(item.get("version", 1)) == 3):
                item["udp"] = True

            proxies.append(item)

        return proxies

    @staticmethod
    def check_protocol(link: str) -> bool:
        return re.match(
            r"^(vmess|trojan|ss|ssr|vless|hysteria|hysteria2|tuic|snell|anytls|socks5|https?)://[a-zA-Z0-9:.?+=@%&#_\-/]{10,}",
            utils.trim(link).replace("\r", ""),
            flags=re.I,
        )

    @staticmethod
    def decode(
        text: str,
        program: str,
        artifact: str = "",
        ignore: bool = False,
        special: bool = False,
        throw: bool = False,
        use_subconverter: bool = True,
        do_verify: bool = True,
    ) -> list[dict[str, object]]:
        def clean_text(document: str) -> str:
            document = utils.trim(text=document)
            if not document:
                return ""

            url_decode = lambda m: (
                f'"name": "{urllib.parse.unquote(m.group(1))}",'
                if m and m.group(1)
                else f'"name": "{utils.random_chars(6)}",'
            )
            document = re.sub(r'"name":(?:\s+)?"(%.*)",', url_decode, document, flags=re.I)

            add_quote = lambda m: f"- '{m.group(1)}'" if m and m.group(1) else f"- '{utils.random_chars(6)}'"
            document = re.sub(r'-\s+("?%.*"?)', add_quote, document, flags=re.I)

            return document

        def load_nodes(document: str) -> list[dict[str, object]]:
            document = quote_unquoted_ipv6(clean_text(document))
            if not document:
                return []

            loaded = None
            try:
                loaded = yaml.load(document, Loader=yaml.SafeLoader)
            except yaml.YAMLError:
                try:
                    yaml.add_multi_constructor(
                        "str",
                        lambda loader, suffix, node: str(node.value),
                        Loader=yaml.SafeLoader,
                    )
                    loaded = yaml.load(document, Loader=yaml.FullLoader)
                except yaml.YAMLError as e:
                    if throw:
                        raise e
                    logger.error(f"cannot load yaml file, artifact: {artifact}, message:\n{traceback.format_exc()}")
                    return []
            except Exception as e:
                if throw:
                    raise e
                logger.error(f"cannot load yaml file, artifact: {artifact}, message:\n{traceback.format_exc()}")
                return []

            if not isinstance(loaded, dict):
                return []
            proxies = loaded.get("proxies", [])
            return proxies if isinstance(proxies, list) else []

        text, nodes = utils.trim(text=text), []
        if not text:
            return []

        is_b64encode, is_json, is_yaml = False, False, False
        if (
            use_subconverter
            or (is_b64encode := utils.isb64encode(text))
            or (is_json := (text.startswith("{") and text.endswith("}")))
            or not (is_yaml := (re.search(r"^proxies:([\s\r\n]+)?$", text, flags=re.MULTILINE) is not None))
        ):
            artifact = utils.trim(text=artifact)
            if not artifact:
                artifact = utils.random_chars(length=6, punctuation=False)

            v2ray_file = os.path.join(PATH, "subconverter", f"{artifact}.txt")
            clash_file = os.path.join(PATH, "subconverter", f"{artifact}.yaml")

            # base64 encoding if all lines start with valid protocol
            if (
                not is_b64encode
                and not is_json
                and not is_yaml
                and all(AirPort.check_protocol(x) for x in text.split("\n") if x and not x.startswith("#"))
            ):
                text = base64.b64encode(text.encode(encoding="UTF8")).decode(encoding="UTF8")

            try:
                with open(v2ray_file, "w+", encoding="UTF8") as f:
                    f.write(text)
                    f.flush()
            except:
                if os.path.exists(v2ray_file):
                    os.remove(v2ray_file)

                logger.error(f"save file failed, artifact: {artifact}")
                traceback.print_exc()

            generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
            success = subconverter.generate_conf(
                generate_conf,
                artifact,
                f"{artifact}.txt",
                f"{artifact}.yaml",
                "clash",
                True,
                True,
                ignore,
            )
            if not success:
                logger.error("cannot generate subconverter config file")
                os.remove(v2ray_file)
                return []

            time.sleep(random.random())
            success = subconverter.convert(binname=program, artifact=artifact)
            logger.info(f"subconverter completed, artifact: [{artifact}]\tsuccess=[{success}]")

            os.remove(v2ray_file)
            if not success:
                return []

            document = ""
            try:
                with open(clash_file, "r", encoding="utf8", errors="ignore") as reader:
                    document = reader.read()
            finally:
                if os.path.exists(clash_file):
                    os.remove(clash_file)
            nodes = load_nodes(document)
        else:
            nodes = load_nodes(text)

        if not nodes:
            return []
        if do_verify:
            return [x for x in nodes if verify(x, special)]
        return nodes

    @staticmethod
    def enable_special_protocols(enabled: bool | None = None) -> bool:
        if enabled is None:
            flag = utils.trim(os.environ.get("ENABLE_SPECIAL_PROTOCOLS", "true")).lower()
            enabled = flag == "" or flag in ["true", "1"]
        return bool(enabled) and is_mihomo()
