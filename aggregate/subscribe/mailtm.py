# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import json
import random
import ssl
import time
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

    id_: str
    from_: Dict
    to: Dict
    subject: str
    intro: str
    text: str
    html: str
    data: Dict


class Account:
    """representing a temprary mailbox."""

    def __init__(self, id: str, address: str, password: str):
        self.id_ = id
        self.address = address
        self.password = password

        jwt = MailTm._make_account_request("token", self.address, self.password)
        self.auth_headers = {
            "Accept": "application/ld+json",
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(jwt["token"]),
        }
        self.api_address = MailTm.api_address

    def get_messages(self, page: int = 1) -> list:
        """download a list of messages currently in the account."""
        content = utils.http_get(
            url="{}/messages?page={}".format(self.api_address, page),
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
                        message_data["id"],
                        message_data["from"],
                        message_data["to"],
                        message_data["subject"],
                        message_data["intro"],
                        text,
                        html,
                        message_data,
                    )
                )
        except:
            print(f"failed to list messages, email: {self.address}")
        return messages

    def delete_account(self, retry: int = 3) -> bool:
        """try to delete the account. returns True if it succeeds."""
        if retry <= 0:
            return False
        try:
            request = urllib.request.Request(
                url=f"{self.api_address}/accounts/{self.id_}",
                headers=self.auth_headers,
                method="DELETE",
            )
            response = urllib.request.urlopen(request, timeout=10, context=CTX)
            status_code = response.getcode()
            return status_code == 204
        except Exception:
            return self.delete_account(retry=retry - 1)

    def monitor_account(self) -> Message:
        """keep waiting for new messages"""
        try:
            while True:
                start = len(self.get_messages())
                while len(self.get_messages()) == start:
                    time.sleep(1)
                return self.get_messages()[0]
        except:
            print(f"cannot get any message from address: {self.address}")
            return None


class MailTm:
    """a python wrapper for mail.tm web api, which is documented here:
    https://api.mail.tm/"""

    api_address = "https://api.mail.tm"

    def _get_domains_list(self, page: int = 1) -> list:
        headers = {"Accept": "application/ld+json"}
        try:
            content = utils.http_get(
                url=f"{self.api_address}/domains?page={page}", headers=headers
            )
            if not content:
                return []

            response = json.loads(content)
            domains = list(
                map(lambda x: x.get("domain", ""), response.get("hydra:member", []))
            )
            return domains
        except:
            return []

    def get_account(self, password: str = None) -> Account:
        """create and return a new account."""
        username = utils.random_chars(
            length=random.randint(8, 12), punctuation=False
        ).lower()
        email_domains = self._get_domains_list()
        if not email_domains:
            print("cannot found any email domains from remote")
            return None

        domain = random.choice(email_domains)
        address = "{}@{}".format(username, domain)
        if not password:
            password = utils.random_chars(
                length=random.randint(8, 16), punctuation=True
            )

        response = self._make_account_request("accounts", address, password)
        if not response or "id" not in response or "address" not in response:
            print("failed to create temporary email")
            return None

        account = Account(response["id"], response["address"], password)
        return account

    @staticmethod
    def _make_account_request(
        endpoint: str, address: str, password: str, retry: int = 3
    ) -> Dict:
        if retry <= 0:
            return {}

        account = {"address": address, "password": password}
        headers = {"Accept": "application/ld+json", "Content-Type": "application/json"}

        data = bytes(json.dumps(account), encoding="UTF8")
        try:
            request = urllib.request.Request(
                url=f"{MailTm.api_address}/{endpoint}",
                data=data,
                headers=headers,
                method="POST",
            )
            response = urllib.request.urlopen(request, context=CTX)
            if not response or response.getcode() not in [200, 201]:
                return {}

            return json.loads(response.read())
        except:
            return MailTm._make_account_request(
                endpoint=endpoint, address=address, password=password, retry=retry - 1
            )
