# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import gzip
import json
import random
import re
import ssl
import time
import traceback
import urllib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict

import utils

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


@dataclass
class Message:
    """simple data class that holds a message information."""

    text: str
    id: str = ""
    sender: Dict = None
    to: Dict = None
    subject: str = ""
    intro: str = ""
    html: str = ""
    data: Dict = None


@dataclass
class Account:
    """representing a temprary mailbox."""

    address: str
    password: str = ""
    id: str = ""


class TemporaryMail(object):
    """temporary mails collctions: https://www.cnblogs.com/perfectdata/p/15902582.html"""

    def __init__(self) -> None:
        self.api_address = ""

    def get_domains_list(self) -> list:
        raise NotImplementedError

    def get_account(self, retry: int = 3) -> Account:
        raise NotImplementedError

    def get_messages(self, account: Account) -> list:
        raise NotImplementedError

    def monitor_account(
        self, account: Account, timeout: int = 300, sleep: int = 3
    ) -> Message:
        """keep waiting for new messages"""
        if not account:
            return None

        timeout = min(600, max(0, timeout))
        sleep = min(max(1, sleep), 10)
        endtime = time.time() + timeout
        try:
            messages = self.get_messages(account=account)
            start = len(messages)

            while True:
                messages = self.get_messages(account=account)
                if len(messages) != start or time.time() >= endtime:
                    break

                time.sleep(sleep)

            if not messages:
                return None

            return messages[0]
        except:
            print(f"cannot get any message from address: {account.address}")

            traceback.print_exc()
            return None

    def delete_account(self, account: Account) -> bool:
        raise NotImplementedError

    def extract_mask(self, text: str, regex: str = "您的验证码是：([0-9]{6})") -> str:
        if not text or not regex:
            return ""
        try:
            return "".join(re.findall(regex, text))
        except:
            print(f"[MaskExtractError] regex exists problems, regex: {regex}")
            return ""

    def generate_address(self, bits: int = 10) -> str:
        bits = min(max(6, bits), 16)
        username = utils.random_chars(length=bits, punctuation=False).lower()
        email_domains = self.get_domains_list()
        if not email_domains:
            print(
                f"[MailTMError] cannot found any email domains from remote, domain: {self.api_address}"
            )
            return ""

        domain = random.choice(email_domains)
        address = "{}@{}".format(username, domain)

        return address


class RootSh(TemporaryMail):
    def __init__(self) -> None:
        self.api_address = "https://rootsh.com"
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.5112.81 Safari/537.36 Edg/104.0.1293.54",
        }

    def get_domains_list(self) -> list:
        content, count = "", 1
        while not content and count <= 3:
            count += 1
            try:
                request = urllib.request.Request(
                    url=self.api_address, headers=self.headers
                )
                response = urllib.request.urlopen(request, timeout=10, context=CTX)
                content = response.read()
                self.headers["Cookie"] = response.getheader("Set-Cookie")
                try:
                    content = str(content, encoding="utf8")
                except:
                    content = gzip.decompress(content).decode("utf8")
            except Exception:
                pass

        if not content:
            return []

        return re.findall(
            '<li><a\s+href="javascript:;">([a-zA-Z0-9\.\-]+)</a></li>', content
        )

    def get_account(self, retry: int = 3) -> Account:
        address = self.generate_address(random.randint(6, 12))
        if not address or retry <= 0:
            return None

        url = f"{self.api_address}/applymail"
        params = {"mail": address}
        self.headers.update(
            {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": self.api_address,
                "Referer": f"{self.api_address}/",
            }
        )

        try:
            data = urllib.parse.urlencode(params).encode(encoding="UTF8")
            request = urllib.request.Request(
                url, data=data, headers=self.headers, method="POST"
            )

            response = urllib.request.urlopen(request, timeout=10, context=CTX)
            if response.getcode() == 200:
                success = json.loads(response.read()).get("success", "false")
                if success == "true":
                    return Account(address=address)

                return None
            else:
                print(
                    "[MailTMError] cannot create email account, domain: {}\tmessage: {}".format(
                        self.api_address, response.read().decode("UTF8")
                    )
                )
                return None
        except:
            return self.get_account(retry=retry - 1)

    def get_messages(self, account: Account) -> list:
        if not account:
            return []

        url = f"{self.api_address}/getmail"
        self.timestamp = int(time.time())
        params = {
            "mail": account.address,
            "time": 0,
            "_": int(time.time() * 1000),
        }

        messages = []
        try:
            data = urllib.parse.urlencode(params).encode(encoding="UTF8")
            request = urllib.request.Request(
                url, data=data, headers=self.headers, method="POST"
            )

            response = urllib.request.urlopen(request, timeout=10, context=CTX)
            if response.getcode() == 200:
                data = json.loads(response.read())
                success = data.get("success", "false")
                if success == "true":
                    emails = data.get("mail", [])
                    for mail in emails:
                        sender = {mail[1]: f"{mail[0]}<{mail[1]}>"}
                        subject = mail[2]
                        address = account.address.replace("@", "(a)").replace(
                            ".", "-_-"
                        )

                        # return 403: Forbidden and cannot found reason
                        url = f"{self.api_address}/win/{address}/{mail[4]}"
                        headers = {
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.5112.81 Safari/537.36 Edg/104.0.1293.54",
                        }

                        content = utils.http_get(url=url, headers=headers)
                        messages.append(
                            Message(
                                sender=sender,
                                to={account.address: account.address},
                                subject=subject,
                                intro=mail[0],
                                text=content,
                                html=content,
                            )
                        )
            else:
                print(
                    f"[MailTMError] cannot get mail list from domain: {self.api_address}, email: {account.address}"
                )
                messages = []
        except:
            messages = []

        return messages

    def delete_account(self, account: Account) -> bool:
        url = f"{self.api_address}/destroymail"
        params = {"_": int(time.time() * 1000)}
        self.headers["Accept"] = "application/json, text/javascript, */*; q=0.01"

        try:
            data = urllib.parse.urlencode(params).encode(encoding="UTF8")
            request = urllib.request.Request(
                url, data=data, headers=self.headers, method="POST"
            )

            response = urllib.request.urlopen(request, timeout=10, context=CTX)
            if response.getcode() == 200:
                success = json.loads(response.read()).get("success", "false")
                return success == "true"
            else:
                print(f"[MailTMError] delete account {account.address} failed")
                return False
        except:
            return False


class SnapMail(TemporaryMail):
    def __init__(self) -> None:
        self.api_address = "https://snapmail.cc"

    def get_domains_list(self) -> list:
        domains = ["snapmail.cc", "lista.cc", "xxxhi.cc"]
        # content = utils.http_get(
        #     url="https://www.snapmail.cc/scripts/controllers/addEmailBox.js", retry=1
        # )
        # if not content:
        #     return domains

        # "scope.emailDomainList = ['snapmail.cc', 'xxxhi.cc', 'lista.cc']"
        # regex = "scope.emailDomainList(?:\s+)?=(?:\s+)?\[(.*)\]"
        # groups = re.findall(regex, content)
        # if not groups:
        #     return domains
        # content = groups[0].replace("'", "")
        # if content:
        #     domains = content.split(",")

        return domains

    def get_account(self, retry: int = 3) -> Account:
        address = self.generate_address(bits=random.randint(6, 12))
        if not address:
            return None

        return Account(address=address)

    def get_messages(self, account: Account) -> list:
        if not account:
            return []

        url = f"{self.api_address}/emaillist/{account.address}"
        content = utils.http_get(url=url, retry=1)
        if not content:
            return []
        try:
            messages, emails = [], json.loads(content)
            for email in emails:
                html = email.get("html", "")
                if not html:
                    continue
                senders = email.get("from", [])
                sender = senders[0] if senders else {}
                messages.append(
                    Message(
                        id=email.get("id", ""),
                        sender=sender,
                        to={account.address, account.address},
                        subject=email.get("subject", ""),
                        text=html,
                        html=html,
                    )
                )

            return messages
        except:
            print(
                f"[MailTMError] cannot get messages, domain: {self.api_address}, address: {account.address}"
            )
            return []

    def delete_account(self, account: Account) -> bool:
        if not account:
            return False

        # url = f"{self.api_address}/user/box/{account.address}"
        # headers = {
        #     "Accept": "application/json, text/plain, */*",
        #     "Accept-Encoding": "gzip, deflate, br",
        #     "Origin": self.api_address,
        #     "Referer": self.api_address + "/",
        #     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.5112.81 Safari/537.36 Edg/104.0.1293.54",
        # }

        # try:
        #     request = urllib.request.Request(url=url, headers=headers, method="DELETE")
        #     response = urllib.request.urlopen(request, timeout=10, context=CTX)
        #     status_code = response.getcode()
        #     return status_code == 204
        # except Exception:
        #     print(
        #         f"[MailTMError] delete account failed, domain: {self.api_address}, address: {account.address}"
        #     )
        #     return False

        print(
            f"[MailTMError] not support delete account, domain: {self.api_address}, address: {account.address}"
        )
        return False


class LinShiEmail(TemporaryMail):
    def __init__(self) -> None:
        self.api_address = "https://linshiyouxiang.net"

    def get_domains_list(self) -> list:
        content = utils.http_get(url=self.api_address)
        if not content:
            return []

        domians = re.findall('data-mailhost="@([a-zA-Z0-9\-_\.]+)"', content)
        return domians

    def get_account(self, retry: int = 3) -> Account:
        address = self.generate_address(bits=random.randint(6, 12))
        if not address:
            return None

        return Account(address=address)

    def get_messages(self, account: Account) -> list:
        if not account:
            return []

        address = account.address.split("@", maxsplit=1)[0]
        url = f"{self.api_address}//api/v1/mailbox/{address}"
        content = utils.http_get(url=url, retry=1)
        if not content:
            return []
        try:
            emails = json.loads(content)
            messages = []
            for email in emails:
                mail_id = email.get("id", "")
                sender = email.get("from", "")
                if not mail_id:
                    continue
                url = f"{self.api_address}/mailbox/{address}/{mail_id}"
                content = utils.http_get(url=url)
                messages.append(
                    Message(
                        id=mail_id,
                        sender={sender: sender},
                        to={account.address: account.address},
                        subject=email.get("subject", ""),
                        text=content,
                        html=content,
                    )
                )
            return messages
        except:
            return []

    def delete_account(self, account: Account) -> bool:
        print(f"[MailTMError] not support delete account, domain: {self.api_address}")
        return True


class MailTM(TemporaryMail):
    """a python wrapper for mail.tm web api, which is documented here: https://api.mail.tm/"""

    def __init__(self) -> None:
        self.api_address = "https://api.mail.tm"
        self.auth_headers = {}

    def get_domains_list(self) -> list:
        headers = {"Accept": "application/ld+json"}
        try:
            content = utils.http_get(
                url=f"{self.api_address}/domains?page=1", headers=headers
            )
            if not content:
                return []

            response = json.loads(content)
            return list(
                map(lambda x: x.get("domain", ""), response.get("hydra:member", []))
            )
        except:
            return []

    def _make_account_request(
        self, endpoint: str, address: str, password: str, retry: int = 3
    ) -> Dict:
        if retry <= 0:
            return {}

        account = {"address": address, "password": password}
        headers = {"Accept": "application/ld+json", "Content-Type": "application/json"}

        data = bytes(json.dumps(account), encoding="UTF8")
        try:
            request = urllib.request.Request(
                url=f"{self.api_address}/{endpoint}",
                data=data,
                headers=headers,
                method="POST",
            )
            response = urllib.request.urlopen(request, timeout=10, context=CTX)
            if not response or response.getcode() not in [200, 201]:
                return {}

            return json.loads(response.read())
        except:
            return self._make_account_request(
                endpoint=endpoint, address=address, password=password, retry=retry - 1
            )

    def _generate_jwt(self, address: str, password: str, retry: int = 3):
        jwt = self._make_account_request(
            endpoint="token", address=address, password=password, retry=retry
        )
        if not jwt:
            print(f"[JWTError] generate jwt token failed, domain: {self.api_address}")
            return

        self.auth_headers = {
            "Accept": "application/ld+json",
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(jwt["token"]),
        }

    def get_account(self, retry: int = 3) -> Account:
        """create and return a new account."""
        address = self.generate_address(random.randint(6, 12))
        if not address:
            return None

        password = utils.random_chars(length=random.randint(8, 16), punctuation=True)
        response = self._make_account_request(
            endpoint="accounts", address=address, password=password, retry=retry
        )
        if not response or "id" not in response or "address" not in response:
            print(
                f"[MailTMError] failed to create temporary email, domain: {self.api_address}"
            )
            return None

        account = Account(
            address=response["address"], password=password, id=response["id"]
        )
        self._generate_jwt(address=address, password=password, retry=retry)

        return account

    def get_messages(self, account: Account) -> list:
        """download a list of messages currently in the account."""
        if not account or not self.auth_headers:
            return []

        content = utils.http_get(
            url="{}/messages?page={}".format(self.api_address, 1),
            headers=self.auth_headers,
            retry=2,
        )

        messages = []
        if not content:
            return messages

        try:
            dataset = json.loads(content).get("hydra:member", [])
            for message_data in dataset:
                content = utils.http_get(
                    url=f"{self.api_address}/messages/{message_data['id']}",
                    headers=self.auth_headers,
                )
                if not content:
                    continue

                data = json.loads(content)
                text = data.get("text", "")
                html = data.get("html", "")
                messages.append(
                    Message(
                        id=message_data["id"],
                        sender=message_data["from"],
                        to=message_data["to"],
                        subject=message_data["subject"],
                        intro=message_data["intro"],
                        text=text,
                        html=html,
                        data=message_data,
                    )
                )
        except:
            print(f"failed to list messages, email: {self.address}")
        return messages

    def delete_account(self, account: Account) -> bool:
        """try to delete the account. returns True if it succeeds."""
        if account is None or not self.auth_headers:
            return False

        try:
            request = urllib.request.Request(
                url=f"{self.api_address}/accounts/{account.id}",
                headers=self.auth_headers,
                method="DELETE",
            )
            response = urllib.request.urlopen(request, timeout=10, context=CTX)
            status_code = response.getcode()
            return status_code == 204
        except Exception:
            print(
                f"[MailTMError] delete account failed, domain: {self.api_address}, address: {account.address}"
            )
            return False


def create_instance() -> TemporaryMail:
    num = random.randint(0, 2)
    if num == 0:
        return SnapMail()
    elif num == 1:
        return LinShiEmail()
    else:
        return MailTM()
