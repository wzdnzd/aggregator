# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import concurrent.futures
import json
import os
import random
import re
import time
import traceback
import urllib
import urllib.parse
import urllib.request

import yaml

import mailtm
import renewal
import subconverter
import utils
from logger import logger

EMAILS_DOMAINS = [
    "@gmail.com",
    "@outlook.com",
    "@163.com",
    "@126.com",
    "@sina.com",
    "@hotmail.com",
    "@qq.com",
    "@foxmail.com",
    "@hotmail.com",
    "@yahoo.com",
]

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

# 判断是否为base64编码
BASE64_PATTERN = re.compile(
    "^([A-Za-z0-9+/]{4})*([A-Za-z0-9+/]{4}|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{2}==)$"
)

# 重命名分隔符
RENAME_SEPARATOR = "#@&#@"

# 标记数字位数
SUFFIX_BITS = 2

# 本地路径协议标识
FILEPATH_PROTOCAL = "file:///"


class AirPort:
    def __init__(
        self,
        name: str,
        site: str,
        sub: str,
        rename: str = "",
        exclude: str = "",
        include: str = "",
        liveness: bool = True,
    ):
        if site.endswith("/"):
            site = site[: len(site) - 1]

        if sub.strip() != "":
            if sub.startswith(FILEPATH_PROTOCAL):
                ref = sub[8:]
            else:
                ref = utils.extract_domain(sub, include_protocal=True)

            self.sub = sub
            self.fetch = ""
            self.ref = ref
            self.reg = ""
            self.registed = True
            self.send_email = ""
        else:
            self.sub = ""
            self.fetch = f"{site}/api/v1/user/server/fetch"
            self.registed = False
            self.send_email = f"{site}/api/v1/passport/comm/sendEmailVerify"
            self.reg = f"{site}/api/v1/passport/auth/register"
            self.ref = site
        self.name = name
        self.rename = rename
        self.exclude = exclude
        self.include = include
        self.liveness = liveness
        self.headers = {"User-Agent": utils.USER_AGENT, "Referer": self.ref}

    @staticmethod
    def get_register_require(
        domain: str, proxy: str = ""
    ) -> tuple[bool, bool, bool, list]:
        domain = utils.extract_domain(url=domain, include_protocal=True)
        if not domain:
            return True, True, True, []

        url = f"{domain}/api/v1/guest/comm/config"
        content = utils.http_get(url=url, retry=2, proxy=proxy)
        if not content or not content.startswith("{") and content.endswith("}"):
            logger.error(f"[QueryError] cannot get register require, domain: {domain}")
            return True, True, True, []

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

            return need_verify, invite_force, recaptcha, whitelist
        except:
            return True, True, True, []

    def sen_email_verify(self, email: str, retry: int = 3) -> bool:
        if not email.strip() or retry <= 0:
            return False
        params = {"email": email.strip()}

        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        headers = self.headers
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            request = urllib.request.Request(
                self.send_email, data=data, headers=headers, method="POST"
            )
            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            if not response or response.getcode() != 200:
                return False

            return json.loads(response.read()).get("data", False)
        except:
            return self.sen_email_verify(email=email, retry=retry - 1)

    def register(
        self, email: str, password: str, email_code: str = None, retry: int = 3
    ) -> tuple[str, str]:
        if retry <= 0:
            return "", ""

        if not password:
            password = utils.random_chars(random.randint(8, 16), punctuation=True)

        params = {
            "email": email,
            "password": password,
            "invite_code": None,
            "email_code": email_code,
        }

        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        headers = self.headers
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            request = urllib.request.Request(
                self.reg, data=data, headers=headers, method="POST"
            )
            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            if not response or response.getcode() != 200:
                return "", ""

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

            if token:
                self.sub = f"{self.ref}/api/v1/client/subscribe?token={token}"
            else:
                subscribe_info = renewal.get_subscribe_info(
                    domain=self.ref, cookies=cookies, authorization=authorization
                )
                if subscribe_info:
                    self.sub = subscribe_info.sub_url
                else:
                    logger.error(
                        f"[RegisterError] cannot get token when register, domain: {self.ref}"
                    )

            return cookies, authorization
        except:
            return self.register(email, password, email_code, retry - 1)

    def order_plan(
        self,
        email: str,
        password: str,
        cookies: str = "",
        authorization: str = "",
        retry: int = 3,
    ) -> bool:
        plan = renewal.get_free_plan(
            domain=self.ref, cookies=cookies, authorization=authorization, retry=retry
        )

        if not plan:
            logger.error(f"not exists free plan, domain: {self.ref}")
            return False
        else:
            logger.info(f"found free plan, domain: {self.ref}, plan: {plan}")

        methods = renewal.get_payment_method(
            domain=self.ref, cookies=cookies, authorization=authorization
        )

        method = random.choice(methods) if methods else 1
        params = {
            "email": email,
            "passwd": password,
            "package": plan.package,
            "plan_id": plan.plan_id,
            "method": method,
            "coupon_code": "",
        }

        success = renewal.flow(
            domain=self.ref,
            params=params,
            reset=False,
            cookies=cookies,
            authorization=authorization,
        )

        if success and (plan.renew or plan.reset):
            logger.info(
                f"[RegisterSuccess] register successed, domain: {self.ref}, address: {email}, passwd: {password}"
            )

        return success

    def fetch_unused(self, cookies: str, auth: str = "", rate: float = 3.0) -> list:
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

    def get_subscribe(self, retry: int) -> tuple[str, str]:
        if self.registed:
            return "", ""

        need_verify, invite_force, recaptcha, whitelist = AirPort.get_register_require(
            self.ref
        )
        # 需要邀请码或者强制验证
        if invite_force or recaptcha or (whitelist and need_verify):
            return "", ""

        if not need_verify:
            email = utils.random_chars(length=random.randint(6, 10), punctuation=False)
            password = utils.random_chars(
                length=random.randint(8, 16), punctuation=True
            )

            email_suffixs = whitelist if whitelist else EMAILS_DOMAINS
            email_domain = random.choice(email_suffixs)
            if not email_domain:
                return "", ""

            email = email + email_domain
            return self.register(email=email, password=password, retry=retry)
        else:
            try:
                mailbox = mailtm.create_instance()
                account = mailbox.get_account()
                if not account:
                    logger.error(f"cannot create account, site: {self.ref}")
                    return "", ""

                message = None
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    starttime = time.time()
                    try:
                        future = executor.submit(
                            mailbox.monitor_account, account, 240, random.randint(1, 3)
                        )
                        success = self.sen_email_verify(email=account.address, retry=3)
                        if not success:
                            executor.shutdown(wait=False)
                            return "", ""
                        message = future.result(timeout=180)
                        logger.info(
                            f"email has been received, domain: {self.ref}\tcost: {int(time.time()- starttime)}s"
                        )
                    except concurrent.futures.TimeoutError:
                        logger.error(
                            f"receiving mail timeout, site: {self.ref}, address: {account.address}"
                        )

                if not message:
                    logger.error(f"cannot receive any message, site: {self.ref}")
                    return "", ""

                # 如果标准正则无法提取验证码则直接匹配数字
                with open("content.html", "w+", encoding="UTF8") as f:
                    f.write(message.text)
                    f.flush()

                mask = mailbox.extract_mask(message.text) or mailbox.extract_mask(
                    message.text, "\s+([0-9]{6})"
                )
                mailbox.delete_account(account=account)
                if not mask:
                    logger.error(f"cannot fetch mask, url: {self.ref}")
                    return "", ""
                return self.register(
                    email=account.address,
                    password=account.password,
                    email_code=mask,
                    retry=retry,
                )
            except:
                return "", ""

    def parse(
        self,
        cookie: str,
        auth: str,
        retry: int,
        rate: float,
        bin_name: str,
        tag: str,
    ) -> list:
        if "" == self.sub:
            logger.error(
                f"[ParseError] cannot found any proxies because subscribe url is empty, domain: {self.ref}"
            )
            return []

        if self.sub.startswith(FILEPATH_PROTOCAL):
            self.sub = self.sub[8:]
            if not os.path.exists(self.sub) or not os.path.isfile(self.sub):
                logger.error(f"[ParseError] file: {self.sub} not found")
                return []

            with open(self.sub, "r", encoding="UTF8") as f:
                text = f.read()
        else:
            text = utils.http_get(
                url=self.sub, headers=self.headers, retry=retry
            ).strip()

            # count = 1
            # while count <= retry:
            #     try:
            #         request = urllib.request.Request(url=self.sub, headers=self.headers)
            #         response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            #         text = str(response.read(), encoding="utf8")

            #         # 读取附件内容
            #         disposition = response.getheader("content-disposition", "")
            #         text = ""
            #         if disposition:
            #             logger.error(str(response.read(), encoding="utf8"))
            #             regex = "(filename)=(\S+)"
            #             content = re.findall(regex, disposition)
            #             if content:
            #                 attachment = os.path.join(
            #                     os.path.abspath(os.path.dirname(__file__)),
            #                     content[0][1],
            #                 )
            #                 if os.path.exists(attachment) or os.path.isfile(attachment):
            #                     text = str(
            #                         open(attachment, "r", encoding="utf8").read(),
            #                         encoding="utf8",
            #                     )
            #                     os.remove(attachment)
            #         else:
            #             text = str(response.read(), encoding="utf8")

            #         break
            #     except:
            #         text = ""

            #     count += 1

        # if "" == text.strip() or not re.match("^[0-9a-zA-Z=]*$", text):
        if "" == text or (text.startswith("{") and text.endswith("}")):
            logger.error(
                f"[ParseError] cannot found any proxies because token is error, domain: {self.ref}"
            )
            return []

        try:
            if BASE64_PATTERN.match(text):
                chars = utils.random_chars(length=3, punctuation=False)
                artifact = f"{self.name}-{chars}"
                v2ray_file = os.path.join(PATH, "subconverter", f"{artifact}.txt")
                clash_file = os.path.join(PATH, "subconverter", f"{artifact}.yaml")

                with open(v2ray_file, "w+") as f:
                    f.write(text)
                    f.flush()

                generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
                success = subconverter.generate_conf(
                    generate_conf,
                    artifact,
                    f"{artifact}.txt",
                    f"{artifact}.yaml",
                    "clash",
                )
                if not success:
                    logger.error("cannot generate subconverter config file")
                    return []

                time.sleep(1)
                success = subconverter.convert(binname=bin_name, artifact=artifact)
                os.remove(v2ray_file)
                if not success:
                    return []

                with open(clash_file, "r", encoding="utf8") as reader:
                    try:
                        config = yaml.load(reader, Loader=yaml.SafeLoader)
                    except yaml.constructor.ConstructorError:
                        reader.seek(0, 0)
                        yaml.add_multi_constructor(
                            "str",
                            lambda loader, suffix, node: None,
                            Loader=yaml.SafeLoader,
                        )
                        config = yaml.load(reader, Loader=yaml.SafeLoader)
                    nodes = config.get("proxies", [])

                # 已经读取，可以删除
                os.remove(clash_file)
            else:
                if not re.search("proxies:", text):
                    logger.error(
                        f"[ParseError] fetch proxies error, domain: {self.ref}"
                    )
                    return []
                try:
                    nodes = yaml.load(text, Loader=yaml.SafeLoader).get("proxies", [])
                except yaml.constructor.ConstructorError:
                    yaml.add_multi_constructor(
                        "str", lambda loader, suffix, node: None, Loader=yaml.SafeLoader
                    )
                    nodes = yaml.load(text, Loader=yaml.FullLoader).get("proxies", [])

            proxies = []
            unused_nodes = self.fetch_unused(cookie, auth, rate)
            for item in nodes:
                name = item.get("name")
                if name in unused_nodes:
                    continue

                try:
                    if self.include and not re.search(self.include, name, re.I):
                        continue
                    else:
                        if self.exclude and re.search(self.exclude, name, re.I):
                            continue

                    # 过滤名字带网址的节点
                    if re.search(
                        "([a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z\u4e00-\u9fa5]{2,}",
                        name,
                    ):
                        continue
                except:
                    logger.error(
                        f"filter proxies error, maybe include or exclude regex exists problems, include: {self.include}\texclude: {self.exclude}"
                    )

                try:
                    if self.rename:
                        if RENAME_SEPARATOR in self.rename:
                            words = self.rename.split(RENAME_SEPARATOR, maxsplit=1)
                            old = words[0].strip()
                            new = words[1].strip()
                            if old:
                                name = re.sub(old, new, name, re.I)
                        else:
                            name = re.sub(self.rename, "", name, re.I)

                except:
                    logger.error(
                        f"rename error, name: {name},\trename: {self.rename}\tseparator: {RENAME_SEPARATOR}\tdomain: {self.ref}"
                    )

                # name = re.sub(r"\[[^\[]*\]|\([^\(]*\)|{[^{]*}|<[^<]*>|【[^【]*】|「[^「]*」", "", name)
                name = re.sub(
                    r"\[[^\[]*\]|\([^\(]*\)|{[^{]*}|<[^<]*>|【[^【]*】|「[^「]*」|[^a-zA-Z0-9\u4e00-\u9fa5_×\.\-|\s]",
                    " ",
                    name,
                )
                name = re.sub("\s+", " ", name).replace("_", "-").strip()
                if not name:
                    continue

                item["name"] = name.upper()

                # 方便标记已有节点，最多留999天
                if "" != tag:
                    if not re.match(f".*-{tag}\d+$", item["name"]):
                        item["name"] = "{}-{}".format(
                            item.get("name"), tag + "1".zfill(SUFFIX_BITS)
                        )
                    else:
                        words = item["name"].rsplit(f"-{tag}")
                        if not words[1].isdigit():
                            continue
                        num = int(words[1]) + 1
                        if num > pow(10, SUFFIX_BITS) - 1:
                            continue

                        num = str(num).zfill(SUFFIX_BITS)
                        name = words[0] + f"-{tag}{num}"
                        item["name"] = name

                # 方便过滤无效订阅
                item["sub"] = self.sub
                item["liveness"] = self.liveness

                proxies.append(item)

            return proxies
        except:
            traceback.print_exc()
            logger.error(
                f"[ParseError] occur error when parse data, domain: {self.ref}"
            )
            return []
