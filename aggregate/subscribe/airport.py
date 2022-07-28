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


class AirPort:
    def __init__(self, name: str, site: str, sub: str):
        if site.endswith("/"):
            site = site[: len(site) - 1]

        if sub.strip() != "":
            self.sub = sub
            self.fetch = ""
            self.ref = utils.extract_domain(sub)
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
            response = urllib.request.urlopen(request, context=CTX)
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
            response = urllib.request.urlopen(request, context=CTX)
            if not response or response.getcode() != 200:
                return "", ""

            token = json.loads(response.read())["data"]["token"]
            cookie = utils.get_cookie(response.getheader("Set-Cookie"))
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
            mailtm = MailTm()
            account = mailtm.get_account()
            if not account:
                print(f"cannot create account, site: {self.ref}")
                return "", ""

            message = None
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(account.monitor_account)
                success = self.sen_email_verify(email=account.address, retry=3)
                if not success:
                    return "", ""
                message = future.result(timeout=250)

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
        #         v2conf = str(response.read(), encoding="utf8")

        #         # 读取附件内容
        #         disposition = response.getheader("content-disposition", "")
        #         v2conf = ""
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
        #                     v2conf = str(
        #                         open(attachment, "r", encoding="utf8").read(),
        #                         encoding="utf8",
        #                     )
        #                     os.remove(attachment)
        #         else:
        #             v2conf = str(response.read(), encoding="utf8")

        #         break
        #     except:
        #         v2conf = ""

        #     count += 1

        v2conf = utils.http_get(url=url, headers=self.headers, retry=retry)
        # if "" == v2conf.strip() or not re.match("^[0-9a-zA-Z=]*$", v2conf):
        if "" == v2conf.strip() or "{" in v2conf:
            return []

        artifact = f"{self.name}{str(index)}"
        v2ray_file = os.path.join(PATH, "subconverter", f"{artifact}.txt")
        clash_file = os.path.join(PATH, "subconverter", f"{artifact}.yaml")

        with open(v2ray_file, "w+") as f:
            f.write(v2conf)
            f.flush()

        generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
        success = subconverter.generate_conf(
            generate_conf, artifact, f"{artifact}.txt", f"{artifact}.yaml", "clash"
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

        proxies = []
        unused_nodes = self.fetch_unused(cookie, rate)
        for item in nodes:
            if item.get("name") in unused_nodes:
                continue

            item["name"] = re.sub(r"[\^\?\:\/]|\s+", " ", item.get("name")).strip()

            if index >= 0:
                mode = index % 26
                factor = index // 26 + 1
                letter = string.ascii_uppercase[mode]
                item["name"] = "{}-{}".format(item.get("name"), letter * factor)

            # 方便标记已有节点，最多留99天
            if "" != tag:
                if not re.match(f".*-{tag}\d+$", item["name"]):
                    item["name"] = "{}-{}".format(item.get("name"), tag + "01")
                else:
                    words = item["name"].rsplit(f"-{tag}")
                    if not words[1].isdigit():
                        continue
                    num = int(words[1]) + 1
                    if num > 99:
                        continue

                    num = "0" + str(num) if num <= 9 else str(num)
                    name = words[0] + f"-{tag}{num}"
                    item["name"] = name

            proxies.append(item)

        return proxies
