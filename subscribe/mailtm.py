# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import gzip
import json
import random
import re
import time
import urllib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.client import HTTPMessage
from typing import IO, Dict

import utils
from logger import logger


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

    def monitor_account(self, account: Account, timeout: int = 300, sleep: int = 3) -> Message:
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
            logger.error(f"cannot get any message from address: {account.address}")
            return None

    def delete_account(self, account: Account) -> bool:
        raise NotImplementedError

    def extract_mask(self, text: str, regex: str = "您的验证码是：([0-9]{6})") -> str:
        if not text or not regex:
            return ""
        try:
            # return "".join(re.findall(regex, text))
            masks = re.findall(regex, text)
            return masks[0] if masks else ""
        except:
            logger.error(f"[MaskExtractError] regex exists problems, regex: {regex}")
            return ""

    def generate_address(self, bits: int = 10) -> str:
        bits = min(max(6, bits), 16)
        username = utils.random_chars(length=bits, punctuation=False).lower()
        email_domains = self.get_domains_list()
        if not email_domains:
            logger.error(f"[MailTMError] cannot found any email domains from remote, domain: {self.api_address}")
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
            "User-Agent": utils.USER_AGENT,
        }

    def get_domains_list(self) -> list:
        content, count = "", 1
        while not content and count <= 3:
            count += 1
            try:
                request = urllib.request.Request(url=self.api_address, headers=self.headers)
                response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
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

        return re.findall(r'<li><a\s+href="javascript:;">([a-zA-Z0-9\.\-]+)</a></li>', content)

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
            request = urllib.request.Request(url, data=data, headers=self.headers, method="POST")

            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            if response.getcode() == 200:
                success = json.loads(response.read()).get("success", "false")
                if success == "true":
                    return Account(address=address)

                return None
            else:
                logger.error(
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
            request = urllib.request.Request(url, data=data, headers=self.headers, method="POST")

            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            if response.getcode() == 200:
                data = json.loads(response.read())
                success = data.get("success", "false")
                if success == "true":
                    emails = data.get("mail", [])
                    for mail in emails:
                        sender = {mail[1]: f"{mail[0]}<{mail[1]}>"}
                        subject = mail[2]
                        address = account.address.replace("@", "(a)").replace(".", "-_-")

                        # return 403: Forbidden and cannot found reason
                        url = f"{self.api_address}/win/{address}/{mail[4]}"
                        headers = {
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                            "User-Agent": utils.USER_AGENT,
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
                logger.info(
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
            request = urllib.request.Request(url, data=data, headers=self.headers, method="POST")

            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            if response.getcode() == 200:
                success = json.loads(response.read()).get("success", "false")
                return success == "true"
            else:
                logger.info(f"[MailTMError] delete account {account.address} failed")
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
            logger.error(f"[MailTMError] cannot get messages, domain: {self.api_address}, address: {account.address}")
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
        #     "User-Agent": utils.USER_AGENT,
        # }

        # try:
        #     request = urllib.request.Request(url=url, headers=headers, method="DELETE")
        #     response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
        #     status_code = response.getcode()
        #     return status_code == 204
        # except Exception:
        #     logger.error(
        #         f"[MailTMError] delete account failed, domain: {self.api_address}, address: {account.address}"
        #     )
        #     return False

        logger.info(f"[MailTMError] not support delete account, domain: {self.api_address}, address: {account.address}")
        return False


class LinShiEmail(TemporaryMail):
    def __init__(self) -> None:
        self.api_address = "https://linshiyouxiang.net"

    def get_domains_list(self) -> list:
        content = utils.http_get(url=self.api_address)
        if not content:
            return []

        domians = re.findall(r'data-mailhost="@([a-zA-Z0-9\-_\.]+)"', content)
        # 该邮箱域名无法接收邮箱，移除
        if "idrrate.com" in domians:
            domians.remove("idrrate.com")

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
        url = f"{self.api_address}/api/v1/mailbox/{address}"
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
        logger.info(f"[MailTMError] not support delete account, domain: {self.api_address}")
        return True


class MailTM(TemporaryMail):
    """a python wrapper for mail.tm web api, which is documented here: https://api.mail.tm/"""

    def __init__(self) -> None:
        self.api_address = "https://api.mail.tm"
        self.auth_headers = {}

    def get_domains_list(self) -> list:
        headers = {"Accept": "application/ld+json"}
        try:
            content = utils.http_get(url=f"{self.api_address}/domains?page=1", headers=headers)
            if not content:
                return []

            response = json.loads(content)
            return list(map(lambda x: x.get("domain", ""), response.get("hydra:member", [])))
        except:
            return []

    def _make_account_request(self, endpoint: str, address: str, password: str, retry: int = 3) -> Dict:
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
            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            if not response or response.getcode() not in [200, 201]:
                return {}

            return json.loads(response.read())
        except:
            return self._make_account_request(endpoint=endpoint, address=address, password=password, retry=retry - 1)

    def _generate_jwt(self, address: str, password: str, retry: int = 3):
        jwt = self._make_account_request(endpoint="token", address=address, password=password, retry=retry)
        if not jwt:
            logger.error(f"[JWTError] generate jwt token failed, domain: {self.api_address}")
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
        response = self._make_account_request(endpoint="accounts", address=address, password=password, retry=retry)
        if not response or "id" not in response or "address" not in response:
            logger.error(f"[MailTMError] failed to create temporary email, domain: {self.api_address}")
            return None

        account = Account(address=response["address"], password=password, id=response["id"])
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
            logger.error(f"failed to list messages, email: {self.address}")
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
            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            status_code = response.getcode()
            return status_code == 204
        except Exception:
            logger.info(f"[MailTMError] delete account failed, domain: {self.api_address}, address: {account.address}")
            return False


class MOAKT(TemporaryMail):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def http_error_302(
            self,
            req: urllib.request.Request,
            fp: IO[bytes],
            code: int,
            msg: str,
            headers: HTTPMessage,
        ) -> IO[bytes]:
            return fp

    def __init__(self) -> None:
        self.api_address = "https://www.moakt.com/zh"
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": self.api_address,
            "Referer": self.api_address,
            "User-Agent": utils.USER_AGENT,
        }

    def get_domains_list(self) -> list:
        content = utils.http_get(url=self.api_address)
        if not content:
            return []

        return re.findall(r'<option\s+value=".*">@([a-zA-Z0-9\.\-_]+)<\/option>', content)

    def _make_account_request(self, username: str, domain: str, retry: int = 3) -> Account:
        if retry <= 0:
            return None

        payload = {
            "domain": domain,
            "username": username,
            "preferred_domain": domain,
            "setemail": "创建",
        }

        data = bytes(json.dumps(payload), encoding="UTF8")
        try:
            # 禁止重定向
            opener = urllib.request.build_opener(self.NoRedirect)
            request = urllib.request.Request(
                url=f"{self.api_address}/inbox",
                data=data,
                headers=self.headers,
                method="POST",
            )
            response = opener.open(request, timeout=10)
            if not response or response.getcode() not in [200, 302]:
                return None

            self.headers["Cookie"] = response.getheader("Set-Cookie")
            return Account(address=f"{username}@{domain}")
        except:
            return self._make_account_request(username=username, domain=domain, retry=retry - 1)

    def get_account(self, retry: int = 3) -> Account:
        address = self.generate_address(bits=random.randint(6, 12))
        if not address or retry <= 0:
            return None

        username, domain = address.split("@", maxsplit=1)
        return self._make_account_request(username=username, domain=domain, retry=retry)

    def get_messages(self, account: Account) -> list:
        if not account:
            return []

        messages = []
        content = utils.http_get(url=f"{self.api_address}/inbox", headers=self.headers)
        if not content:
            return messages

        mails = re.findall(r'<a\s+href="/zh(/email/[a-z0-9\-]+)">', content)
        if not mails:
            return messages

        for mail in mails:
            url = f"{self.api_address}{mail}/content/"
            content = utils.http_get(url=url, headers=self.headers)
            if not content:
                continue
            messages.append(Message(text=content, html=content))
        return messages

    def delete_account(self, account: Account) -> bool:
        if not account:
            return False

        utils.http_get(url=f"{self.api_address}/inbox/logout", headers=self.headers)
        return True


class Emailnator(TemporaryMail):
    def __init__(self, onlygmail: bool = False) -> None:
        self.api_address = "https://www.emailnator.com"
        self.only_gmail = onlygmail
        self.headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "User-Agent": utils.USER_AGENT,
            "Content-Type": "application/json",
            "Origin": "https://www.emailnator.com",
            "Referer": "https://www.emailnator.com/",
        }

    def get_domains_list(self) -> list:
        # unable to obtain the supported email domain through web api
        return ["gmail.com", "googlemail.com", "smartnator.com", "psnator.com", "tmpmailtor.com", "mydefipet.live"]

    def _get_xsrf_token(self, retry: int = 3) -> tuple[str, str]:
        cookies, xsrf_token, count = "", "", 1
        while not cookies and count <= retry:
            count += 1
            try:
                request = urllib.request.Request(url=self.api_address, headers=self.headers)
                response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)

                cookies = response.getheader("Set-Cookie")
                groups = re.findall("XSRF-TOKEN=(.+?);", cookies)
                xsrf_token = groups[0] if groups else ""
                xsrf_token = urllib.parse.unquote(xsrf_token, encoding="utf8", errors="replace")

                groups = re.findall("(XSRF-TOKEN|gmailnator_session)=(.+?);", cookies)
                cookies = ";".join(["=".join(x) for x in groups]).strip() if groups else cookies
            except Exception:
                pass

        return cookies, xsrf_token

    def get_account(self, retry: int = 3) -> Account:
        cookie, xsrf_token = self._get_xsrf_token(retry=3)
        if retry <= 0 or not cookie or not xsrf_token:
            logger.error(
                f"[EmailnatorError] cannot create account because cannot get cookies or xsrf_token or archieved max retry, domain: {self.api_address}"
            )
            return None

        self.headers["Cookie"] = cookie
        self.headers["X-XSRF-TOKEN"] = xsrf_token

        url = f"{self.api_address}/generate-email"
        params = ["plusGmail", "dotGmail"] if self.only_gmail else ["domain", "plusGmail", "dotGmail", "googleMail"]

        try:
            data = bytes(json.dumps({"email": params}), "UTF8")
            request = urllib.request.Request(url, data=data, headers=self.headers, method="POST")
            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            if response.getcode() == 200:
                content = response.read()
                try:
                    content = str(content, encoding="utf8")
                except:
                    content = gzip.decompress(content).decode("utf8")

                emails = json.loads(content).get("email", [])
                return Account(emails[0]) if emails else None
            else:
                logger.error(
                    "[EmailnatorError] cannot create email account, domain: {}\tmessage: {}".format(
                        self.api_address, response.read().decode("UTF8")
                    )
                )
                return None
        except:
            return self.get_account(retry=retry - 1)

    def get_messages(self, account: Account) -> list:
        if not account:
            return []
        try:
            content, messages = self._get_messages(address=account.address), []
            if not content:
                return messages

            dataset = json.loads(content).get("messageData", [])
            for data in dataset:
                messageid = data.get("messageID", "")
                # AD
                if not utils.isb64encode(content=messageid, padding=False):
                    continue

                content = self._get_messages(address=account.address, messageid=messageid)
                messages.append(
                    Message(
                        subject=data.get("subject", ""),
                        id=messageid,
                        sender={data.get("from", ""), data.get("from", "")},
                        html=content,
                        text=content,
                    )
                )
            return messages
        except:
            return []

    def _get_messages(self, address: str, messageid: str = "", retry: int = 3) -> str:
        if not address or retry <= 0:
            logger.error(
                f"[EmailnatorError] cannot list messages because address is empty or archieved max retry, domain: {self.api_address}"
            )
            return ""

        url = f"{self.api_address}/message-list"
        params = {"email": address}
        if not utils.isblank(messageid):
            params["messageID"] = messageid

        try:
            data = data = bytes(json.dumps(params), "UTF8")
            request = urllib.request.Request(url, data=data, headers=self.headers, method="POST")
            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            content = ""
            if response.getcode() == 200:
                content = response.read()
                try:
                    content = str(content, encoding="utf8")
                except:
                    content = gzip.decompress(content).decode("utf8")

            return content
        except:
            return self._get_messages(address=address, messageid=messageid, retry=retry - 1)

    def delete_account(self, account: Account) -> bool:
        logger.info(f"[EmailnatorError] not support delete account, domain: {self.api_address}")
        return True


def create_instance(only_gmail: bool = False) -> TemporaryMail:
    if only_gmail:
        return Emailnator(onlygmail=True)

    num = random.randint(0, 1)
    if num == 1:
        return MailTM()
    else:
        return MOAKT()
