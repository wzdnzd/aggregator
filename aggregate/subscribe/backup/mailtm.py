# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import json
import random
import re
import sys
import time
from dataclasses import dataclass
from typing import Dict

import func_timeout
from func_timeout import func_set_timeout
from aggregate.subscribe.utils import random_chars

import requests


@dataclass
class Message:
    """Simple data class that holds a message information."""

    id_: str
    from_: Dict
    to: Dict
    subject: str
    intro: str
    text: str
    html: str
    data: Dict


class Account:
    """Representing a temprary mailbox."""

    def __init__(self, id: str, address: str, password: str):
        self.id_ = id
        self.address = address
        self.password = password

        jwt = MailTm._make_account_request("token", self.address, self.password)
        self.auth_headers = {
            "accept": "application/ld+json",
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(jwt["token"]),
        }
        self.api_address = MailTm.api_address

    def get_messages(self, page: int = 1) -> list:
        """Download a list of messages currently in the account."""
        r = requests.get(
            "{}/messages?page={}".format(self.api_address, page),
            headers=self.auth_headers,
        )
        messages = []
        for message_data in r.json()["hydra:member"]:
            r = requests.get(
                f"{self.api_address}/messages/{message_data['id']}",
                headers=self.auth_headers,
            )
            text = r.json()["text"]
            html = r.json()["html"]
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
        return messages

    def delete_account(self) -> bool:
        """Try to delete the account. Returns True if it succeeds."""
        r = requests.delete(
            "{}/accounts/{}".format(self.api_address, self.id_),
            headers=self.auth_headers,
        )
        return r.status_code == 204

    def monitor_account(self, timeout: int = 300) -> Message:
        @func_set_timeout(timeout)
        def _monitor() -> Message:
            """Keep waiting for new messages"""
            while True:
                start = len(self.get_messages())
                while len(self.get_messages()) == start:
                    time.sleep(1)
                return self.get_messages()[0]

        timeout = max(0, timeout)
        try:
            return _monitor()
        except func_timeout.exceptions.FunctionTimedOut:
            print(f"cannot get any message from address: {self.address}")
            return None


class CouldNotGetAccountException(Exception):
    """Raised if a POST on /accounts or /authorization_token return a failed status code."""


class InvalidDbAccountException(Exception):
    """Raised if an account could not be recovered from the db file."""


class MailTm:
    """A python wrapper for mail.tm web api, which is documented here:
    https://api.mail.tm/"""

    api_address = "https://api.mail.tm"

    def _get_domains_list(self) -> list:
        r = requests.get("{}/domains".format(self.api_address))
        response = r.json()
        domains = list(map(lambda x: x["domain"], response["hydra:member"]))
        return domains

    def get_account(self, password: str = None) -> Account:
        """Create and return a new account."""
        username = random_chars(length=random.randint(8, 12), punctuation=False).lower()
        domain = random.choice(self._get_domains_list())
        address = "{}@{}".format(username, domain)
        if not password:
            password = random_chars(length=random.randint(8, 16), punctuation=True)

        response = self._make_account_request("accounts", address, password)
        account = Account(response["id"], response["address"], password)
        return account

    @staticmethod
    def _make_account_request(endpoint: str, address: str, password: str) -> Dict:
        account = {"address": address, "password": password}
        headers = {"accept": "application/ld+json", "Content-Type": "application/json"}
        r = requests.post(
            "{}/{}".format(MailTm.api_address, endpoint),
            data=json.dumps(account),
            headers=headers,
        )
        if r.status_code not in [200, 201]:
            raise CouldNotGetAccountException()
        return r.json()


if __name__ == "__main__":
    mailtm = MailTm()
    account = mailtm.get_account()
    if not account:
        print("cannot create account")
        sys.exit(-1)

    print(account.address)
    message = account.monitor_account(180)
    if message:
        print(message.text)
        content = message.text
        mask = "".join(re.findall("[0-9]{6}", content))
        print(mask)
