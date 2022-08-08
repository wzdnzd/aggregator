# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import concurrent.futures
import json
import os
import random
import re
import ssl
import string
import time
import traceback
import urllib
import urllib.parse
import urllib.request

import yaml

import subconverter
import utils
from mailtm import MailTm

EMAILS_DOMAINS = [
    "@gmail.com",
    "@outlook.com",
    "@163.com",
    "@126.com",
    "@sina.com",
    "@hotmail.com",
    "@qq.com",
    "@foxmail.com",
]

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 判断是否为base64编码
BASE64_PATTERN = re.compile(
    "^([A-Za-z0-9+/]{4})*([A-Za-z0-9+/]{4}|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{2}==)$"
)

# 重命名分隔符
RENAME_SEPARATOR = "#@&#@"

# 标记数字位数
SUFFIX_BITS = 2


class AirPort:
    def __init__(
        self, name: str, site: str, sub: str, rename: str = "", exclude: str = ""
    ):
        if site.endswith("/"):
            site = site[: len(site) - 1]

        if sub.strip() != "":
            self.sub = sub
            self.fetch = ""
            self.ref = utils.extract_domain(sub, include_protocal=True)
            self.reg = ""
            self.registed = True
            self.send_email = ""
        else:
            self.sub = f"{site}/api/v1/client/subscribe?token="
            self.fetch = f"{site}/api/v1/user/server/fetch"
            self.registed = False
            self.send_email = f"{site}/api/v1/passport/comm/sendEmailVerify"
            self.reg = f"{site}/api/v1/passport/auth/register"
            self.ref = site
        self.name = name
        self.rename = rename
        self.exclude = exclude
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.114 Safari/537.36 Edg/103.0.1264.62",
            "Referer": self.ref,
        }

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
            response = urllib.request.urlopen(request, timeout=10, context=CTX)
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
            response = urllib.request.urlopen(request, timeout=10, context=CTX)
            if not response or response.getcode() != 200:
                return "", ""

            token = json.loads(response.read())["data"]["token"]
            cookie = utils.extract_cookie(response.getheader("Set-Cookie"))
            subscribe = self.sub + token
            return subscribe, cookie
        except:
            return self.register(email, password, retry - 1)

    def fetch_unused(self, cookie: str, rate: float) -> list:
        if "" == cookie.strip() or "" == self.fetch.strip():
            return []

        self.headers["Cookie"] = cookie
        try:
            proxies = []
            request = urllib.request.Request(self.fetch, headers=self.headers)
            response = urllib.request.urlopen(request, timeout=5, context=CTX)
            if response.getcode() != 200:
                return proxies

            datas = json.loads(response.read())["data"]
            for item in datas:
                if float(item.get("rate", "1.0")) > rate:
                    proxies.append(item.get("name"))

            return proxies
        except:
            return []

    def get_subscribe(self, retry: int, need_verify: bool) -> tuple[str, str]:
        if self.registed:
            return self.sub, ""

        if not need_verify:
            email = utils.random_chars(length=random.randint(6, 10), punctuation=False)
            password = utils.random_chars(
                length=random.randint(8, 16), punctuation=True
            )
            email = email + random.choice(EMAILS_DOMAINS)
            return self.register(email=email, password=password, retry=retry)
        else:
            try:
                mailtm = MailTm()
                account = mailtm.get_account()
                if not account:
                    print(f"cannot create account, site: {self.ref}")
                    return "", ""

                message = None
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(account.monitor_account, 240)
                    success = self.sen_email_verify(email=account.address, retry=3)
                    if not success:
                        executor.shutdown(wait=False)
                        return "", ""
                    message = future.result(timeout=240)

                if not message:
                    print(f"cannot receive any message, site: {self.ref}")
                    return "", ""
                content = message.text
                mask = "".join(re.findall("[0-9]{6}", content))
                account.delete_account(retry=2)
                if not mask:
                    print(f"cannot fetch mask, url: {self.ref}")
                    return "", ""
                return self.register(
                    email=account.address,
                    password=account.password,
                    email_code=mask,
                    retry=retry,
                )
            except:
                traceback.print_exc()
                return "", ""

    def parse(
        self,
        url: str,
        cookie: str,
        retry: int,
        rate: float,
        index: int,
        bin_name: str,
        tag: str,
    ) -> list:
        if "" == url:
            return []

        # count = 1
        # while count <= retry:
        #     try:
        #         request = urllib.request.Request(url=url, headers=self.headers)
        #         response = urllib.request.urlopen(request, timeout=10, context=CTX)
        #         text = str(response.read(), encoding="utf8")

        #         # 读取附件内容
        #         disposition = response.getheader("content-disposition", "")
        #         text = ""
        #         if disposition:
        #             print(str(response.read(), encoding="utf8"))
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

        text = utils.http_get(url=url, headers=self.headers, retry=retry).strip()
        # if "" == text.strip() or not re.match("^[0-9a-zA-Z=]*$", text):
        if "" == text or (text.startswith("{") and text.endswith("}")):
            return []

        chars = utils.random_chars(length=3, punctuation=False)
        suffix = f"-{index}-{chars}" if index >= 0 else f"{index}-{chars}"
        artifact = f"{self.name}{suffix}"
        v2ray_file = os.path.join(PATH, "subconverter", f"{artifact}.txt")
        clash_file = os.path.join(PATH, "subconverter", f"{artifact}.yaml")

        try:
            if BASE64_PATTERN.match(text):
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
                    print("cannot generate subconverter config file")
                    return []

                time.sleep(1)
                success = subconverter.convert(binname=bin_name, artifact=artifact)
                os.remove(v2ray_file)
                if not success:
                    return []

                with open(clash_file, "r", encoding="utf8") as reader:
                    config = yaml.load(reader, Loader=yaml.SafeLoader)
                    nodes = config.get("proxies", [])

                # 已经读取，可以删除
                os.remove(clash_file)
            else:
                nodes = yaml.load(text, Loader=yaml.SafeLoader).get("proxies", [])

            proxies = []
            unused_nodes = self.fetch_unused(cookie, rate)
            for item in nodes:
                name = item.get("name")
                if name in unused_nodes:
                    continue
                if self.exclude:
                    try:
                        if re.search(self.exclude, name):
                            continue
                    except:
                        print(
                            f"filter proxies error, maybe exclude regex exists problems, exclude: {self.exclude}"
                        )

                name = re.sub(r"[\^\?\:\/]|\(.*\)", "", name)
                if self.rename and RENAME_SEPARATOR in self.rename:
                    try:
                        words = self.rename.split(RENAME_SEPARATOR, maxsplit=1)
                        old = words[0].strip()
                        new = words[1].strip()
                        if old:
                            name = re.sub(old, new, name)
                    except:
                        print(
                            f"rename error, name: {name},\trename: {self.rename}\tseparator: {RENAME_SEPARATOR}\tdomain: {self.ref}"
                        )

                name = re.sub("\s+", " ", name).replace("_", "-").strip()
                item["name"] = name

                if index >= 0:
                    mode = index % 26
                    factor = index // 26 + 1
                    letter = string.ascii_uppercase[mode]
                    if factor > 1:
                        item["name"] = "{}-{}{}".format(
                            item.get("name"), factor, letter
                        )
                    else:
                        item["name"] = "{}-{}".format(item.get("name"), letter)

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
                item["sub"] = url
                proxies.append(item)

            return proxies
        except:
            print(f"[ParseError] occur error when parse data, url: {self.ref}")
            return []
