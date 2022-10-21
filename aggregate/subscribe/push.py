# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import json
import os
import traceback
import urllib
import urllib.parse
import urllib.request

import utils
from logger import logger


class PushTo(object):
    def __init__(self, token: str = "") -> None:
        self.api_address = ""
        self.name = ""
        self.token = "" if not token or not isinstance(token, str) else token

    def push_file(
        self, filepath: str, push_conf: dict, group: str = "", retry: int = 5
    ) -> bool:
        if not os.path.exists(filepath) or not os.path.isfile(filepath):
            logger.error(f"[PushFileError] file {filepath} not found")
            return False

        content = " "
        with open(filepath, "r", encoding="utf8") as f:
            content = f.read()

        return self.push_to(
            content=content, push_conf=push_conf, group=group, retry=retry
        )

    def push_to(
        self, content: str, push_conf: dict, group: str = "", retry: int = 5
    ) -> bool:
        raise NotImplementedError

    def validate(self, push_conf: dict) -> bool:
        raise NotImplementedError

    def filter_push(self, push_conf: dict) -> dict:
        raise NotImplementedError

    def raw_url(self, fileid: str, folderid: str = "", username: str = "") -> str:
        raise NotImplementedError


class PushToPaste(PushTo):
    """https://paste.gg"""

    def __init__(self, token: str) -> None:
        super().__init__(token=token)
        self.api_address = "https://api.paste.gg/v1/pastes"
        self.name = "paste.gg"

    def push_to(
        self, content: str, push_conf: dict, group: str = "", retry: int = 5
    ) -> bool:
        if not self.validate(push_conf=push_conf):
            logger.error(f"[PushError] push config is invalidate, domain: {self.name}")
            return False

        url, data, headers = self._generate_payload(
            content=content, push_conf=push_conf
        )

        try:
            request = urllib.request.Request(
                url, data=data, headers=headers, method="PATCH"
            )
            response = urllib.request.urlopen(request, timeout=15, context=utils.CTX)
            if self._is_success(response.getcode()):
                logger.info(
                    f"[PushSuccess] push subscribes information to {self.name} successed, group=[{group}]"
                )
                return True
            else:
                logger.info(
                    "[PushError]: group=[{}], name: {}, error message: \n{}".format(
                        group, self.name, response.read().decode("unicode_escape")
                    )
                )
                return False

        except Exception:
            self._error_handler(group=group)

            retry -= 1
            if retry > 0:
                return self.push_to(content, push_conf, group, retry)

            return False

    def validate(self, push_conf: dict) -> bool:
        if not push_conf:
            return False

        folderid = push_conf.get("folderid", "")
        fileid = push_conf.get("fileid", "")

        return (
            "" != self.token.strip() and "" != folderid.strip() and "" != fileid.strip()
        )

    def _generate_payload(self, content: str, push_conf: dict) -> tuple[str, str, dict]:
        folderid = push_conf.get("folderid", "")
        fileid = push_conf.get("fileid", "")

        headers = {
            "Authorization": f"Key {self.token}",
            "Content-Type": "application/json",
        }
        data = json.dumps({"content": {"format": "text", "value": content}}).encode(
            "UTF8"
        )
        url = f"{self.api_address}/{folderid}/files/{fileid}"

        return url, data, headers

    def _is_success(self, status_code: int) -> bool:
        return status_code == 204

    def _error_handler(self, group: str = "") -> None:
        logger.error(
            f"[PushError]: group=[{group}], name: {self.name}, error message: \n{traceback.format_exc()}"
        )

    def filter_push(self, push_conf: dict) -> dict:
        configs = {}
        for k, v in push_conf.items():
            if (
                self.token
                and v.get("folderid", "")
                and v.get("fileid", "")
                and v.get("username", "")
            ):
                configs[k] = v

        return configs

    def raw_url(self, fileid: str, folderid: str = "", username: str = "") -> str:
        if not fileid or not folderid or not username:
            return ""

        return f"https://paste.gg/p/{username}/{folderid}/files/{fileid}/raw"


class PushToFarsEE(PushTo):
    """https://fars.ee"""

    def __init__(self) -> None:
        super().__init__()
        self.name = "fars.ee"
        self.api_address = "https://fars.ee"

    def push_to(
        self, content: str, push_conf: dict, group: str = "", retry: int = 5
    ) -> bool:
        if not self.validate(push_conf=push_conf):
            logger.error(f"[PushError] push config is invalidate, name: {self.name}")
            return False

        if retry <= 0:
            logger.error(f"[PushError] achieve max retry, name: {self.name}")
            return False

        uuid = push_conf.get("uuid", "")
        headers = {"Content-Type": "application/json"}
        data = json.dumps({"content": content, "private": 1}).encode("UTF8")
        url = f"{self.api_address}/{uuid}"

        try:
            request = urllib.request.Request(
                url, data=data, headers=headers, method="PUT"
            )
            response = urllib.request.urlopen(request, timeout=15, context=utils.CTX)
            if response.getcode() == 200:
                logger.info(
                    f"[PushSuccess] push subscribes information to {self.name} successed, group=[{group}]"
                )
                return True
            else:
                logger.info(
                    "[PushError]: group=[{}], name: {}, error message: \n{}".format(
                        group, self.name, response.read().decode("unicode_escape")
                    )
                )
                return False

        except Exception:
            logger.error(
                f"[PushError]: group=[{group}], name: {self.name}, error message:"
            )
            traceback.print_exc()

            return self.push_to(content, push_conf, group, retry - 1)

    def validate(self, push_conf: dict) -> bool:
        return push_conf is not None and push_conf.get("uuid", "")

    def filter_push(self, push_conf: dict) -> dict:
        configs = {}
        for k, v in push_conf.items():
            if v and v.get("uuid", ""):
                configs[k] = v

        return configs

    def raw_url(self, fileid: str, folderid: str = "", username: str = "") -> str:
        return f"{self.api_address}/{fileid}"


class PushToDrift(PushTo):
    """waitting for public api"""

    def __init__(self, token: str) -> None:
        super().__init__()
        self.name = "drift.lol"
        self.api_address = "https://www.drift.lol"

    def push_to(
        self, content: str, push_conf: dict, group: str = "", retry: int = 5
    ) -> bool:
        return super().push_to(content, push_conf, group, retry)

    def validate(self, push_conf: dict) -> bool:
        return super().validate(push_conf)

    def filter_push(self, push_conf: dict) -> dict:
        return super().filter_push(push_conf)

    def raw_url(self, fileid: str, folderid: str = "", username: str = "") -> str:
        return super().raw_url(fileid, folderid, username)


class PushToDevbin(PushToPaste):
    """https://devbin.dev"""

    def __init__(self, token: str) -> None:
        super().__init__(token=token)
        self.name = "devbin.dev"
        self.api_address = "https://devbin.dev/api/v3/paste"

    def validate(self, push_conf: dict) -> bool:
        if not push_conf:
            return False

        fileid = push_conf.get("fileid", "")
        return "" != self.token.strip() and "" != fileid.strip()

    def filter_push(self, push_conf: dict) -> dict:
        configs = {}
        for k, v in push_conf.items():
            if v.get("fileid", "") and self.token:
                configs[k] = v

        return configs

    def _generate_payload(self, content: str, push_conf: dict) -> tuple[str, str, dict]:
        fileid = push_conf.get("fileid", "")

        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "Accept": "*/*",
        }
        data = json.dumps({"content": content, "syntaxName": "auto"}).encode("UTF8")
        url = f"{self.api_address}/{fileid}"

        return url, data, headers

    def _is_success(self, status_code: int) -> bool:
        return status_code == 201

    def _error_handler(self, group: str = "") -> None:
        super()._error_handler(group)

        # TODO: waitting for product enviroment api
        self.api_address = "https://beta.devbin.dev/api/v3/paste"

    def raw_url(self, fileid: str, folderid: str = "", username: str = "") -> str:
        if not fileid:
            return ""

        return f"https://devbin.dev/Raw/{fileid}"


def get_instance(push_type: int = 1) -> PushTo:
    token = os.environ.get("PUSH_TOKEN", "").strip()
    if not token:
        raise ValueError(
            f"[PushError] not found 'PUSH_TOKEN' in environment variables, please check it and try again"
        )

    if push_type == 1:
        return PushToDevbin(token=token)

    return PushToPaste(token=token)
