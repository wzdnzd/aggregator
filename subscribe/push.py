# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import json
import os
import traceback
import urllib
import urllib.parse
import urllib.request
from http.client import HTTPResponse

import utils
from logger import logger
from urlvalidator import isurl


class PushTo(object):
    def __init__(self, token: str = "") -> None:
        self.api_address = ""
        self.name = ""
        self.method = "PUT"
        self.token = "" if not token or not isinstance(token, str) else token

    def _storage(self, content: str, filename: str, folder: str = "") -> bool:
        if not content or not filename:
            return False

        basedir = os.path.abspath(os.environ.get("LOCAL_BASEDIR", ""))
        try:
            savepath = os.path.abspath(os.path.join(basedir, folder, filename))
            os.makedirs(os.path.dirname(savepath), exist_ok=True)
            with open(savepath, "w+", encoding="utf8") as f:
                f.write(content)
                f.flush()

            return True
        except:
            return False

    def push_file(self, filepath: str, push_conf: dict, group: str = "", retry: int = 5) -> bool:
        if not os.path.exists(filepath) or not os.path.isfile(filepath):
            logger.error(f"[PushFileError] file {filepath} not found")
            return False

        content = " "
        with open(filepath, "r", encoding="utf8") as f:
            content = f.read()

        return self.push_to(content=content, push_conf=push_conf, group=group, retry=retry)

    def push_to(self, content: str, push_conf: dict, group: str = "", retry: int = 5, **kwargs) -> bool:
        if not self.validate(push_conf=push_conf):
            logger.error(f"[PushError] push config is invalidate, domain: {self.name}")
            return False

        if push_conf.get("local", ""):
            self._storage(content=content, filename=push_conf.get("local"))

        url, data, headers = self._generate_payload(content=content, push_conf=push_conf)
        payload = kwargs.get("payload", None)
        if payload and isinstance(payload, dict):
            try:
                data = json.dumps(payload).encode("UTF8")
            except:
                logger.error(f"[PushError] invalid payload, domain: {self.name}")
                return False

        try:
            request = urllib.request.Request(url=url, data=data, headers=headers, method=self.method)
            response = urllib.request.urlopen(request, timeout=60, context=utils.CTX)
            if self._is_success(response):
                logger.info(f"[PushSuccess] push subscribes information to {self.name} successed, group=[{group}]")
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

    def _is_success(self, response: HTTPResponse) -> bool:
        return response and response.getcode() == 200

    def _generate_payload(self, content: str, push_conf: dict) -> tuple[str, str, dict]:
        raise NotImplementedError

    def _error_handler(self, group: str = "") -> None:
        logger.error(f"[PushError]: group=[{group}], name: {self.name}, error message: \n{traceback.format_exc()}")

    def validate(self, push_conf: dict) -> bool:
        raise NotImplementedError

    def filter_push(self, push_conf: dict) -> dict:
        raise NotImplementedError

    def raw_url(self, push_conf: dict) -> str:
        raise NotImplementedError


class PushToPasteGG(PushTo):
    """https://paste.gg"""

    def __init__(self, token: str) -> None:
        super().__init__(token=token)
        self.api_address = "https://api.paste.gg/v1/pastes"
        self.name = "paste.gg"
        self.method = "PATCH"

    def validate(self, push_conf: dict) -> bool:
        if not push_conf or type(push_conf) != dict:
            return False

        folderid = push_conf.get("folderid", "")
        fileid = push_conf.get("fileid", "")

        return "" != self.token.strip() and "" != folderid.strip() and "" != fileid.strip()

    def _generate_payload(self, content: str, push_conf: dict) -> tuple[str, str, dict]:
        folderid = push_conf.get("folderid", "")
        fileid = push_conf.get("fileid", "")

        headers = {
            "Authorization": f"Key {self.token}",
            "Content-Type": "application/json",
            "User-Agent": utils.USER_AGENT,
        }
        data = json.dumps({"content": {"format": "text", "value": content}}).encode("UTF8")
        url = f"{self.api_address}/{folderid}/files/{fileid}"

        return url, data, headers

    def _is_success(self, response: HTTPResponse) -> bool:
        return response and response.getcode() == 204

    def _error_handler(self, group: str = "") -> None:
        logger.error(f"[PushError]: group=[{group}], name: {self.name}, error message: \n{traceback.format_exc()}")

    def filter_push(self, push_conf: dict) -> dict:
        configs = {}
        for k, v in push_conf.items():
            if self.token and v.get("folderid", "") and v.get("fileid", "") and v.get("username", ""):
                configs[k] = v

        return configs

    def raw_url(self, push_conf: dict) -> str:
        if not push_conf or type(push_conf) != dict:
            return ""

        fileid = push_conf.get("fileid", "")
        folderid = push_conf.get("folderid", "")
        username = push_conf.get("username", "")

        if not fileid or not folderid or not username:
            return ""

        return f"https://paste.gg/p/{username}/{folderid}/files/{fileid}/raw"


class PushToFarsEE(PushTo):
    """https://fars.ee"""

    def __init__(self) -> None:
        super().__init__()
        self.name = "fars.ee"
        self.api_address = "https://fars.ee"
        self.method = "PUT"

    def _generate_payload(self, content: str, push_conf: dict) -> tuple[str, str, dict]:
        uuid = push_conf.get("uuid", "")
        headers = {"Content-Type": "application/json"}
        data = json.dumps({"content": content, "private": 1}).encode("UTF8")
        url = f"{self.api_address}/{uuid}"

        return url, data, headers

    def validate(self, push_conf: dict) -> bool:
        return push_conf is not None and type(push_conf) == dict and push_conf.get("uuid", "")

    def filter_push(self, push_conf: dict) -> dict:
        configs = {}
        for k, v in push_conf.items():
            if v and v.get("uuid", ""):
                configs[k] = v

        return configs

    def raw_url(self, push_conf: dict) -> str:
        if not push_conf or type(push_conf) != dict or not push_conf.get("fileid", ""):
            return ""

        fileid = push_conf.get("fileid", "")
        return f"{self.api_address}/{fileid}"


class PushToDevbin(PushToPasteGG):
    """https://devbin.dev"""

    def __init__(self, token: str) -> None:
        super().__init__(token=token)
        self.name = "devbin.dev"
        self.api_address = "https://devbin.dev/api/v3/paste"

    def validate(self, push_conf: dict) -> bool:
        if not push_conf or type(push_conf) != dict:
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

    def _is_success(self, response: HTTPResponse) -> bool:
        return response and response.getcode() == 201

    def _error_handler(self, group: str = "") -> None:
        super()._error_handler(group)

        # TODO: waitting for product enviroment api
        self.api_address = "https://beta.devbin.dev/api/v3/paste"

    def raw_url(self, push_conf: dict) -> str:
        if not push_conf or type(push_conf) != dict or not push_conf.get("fileid", ""):
            return ""

        fileid = push_conf.get("fileid", "")

        return f"https://devbin.dev/Raw/{fileid}"


class PushToPastefy(PushToDevbin):
    """https://pastefy.ga"""

    def __init__(self, token: str) -> None:
        super().__init__(token)
        self.name = "pastefy.ga"
        self.api_address = "https://pastefy.ga/api/v2/paste"
        self.method = "PUT"

    def _generate_payload(self, content: str, push_conf: dict) -> tuple[str, str, dict]:
        fileid = push_conf.get("fileid", "")

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": utils.USER_AGENT,
        }
        data = json.dumps({"content": content}).encode("UTF8")
        url = f"{self.api_address}/{fileid}"

        return url, data, headers

    def _is_success(self, response: HTTPResponse) -> bool:
        if not response or response.getcode() != 200:
            return False

        try:
            return json.loads(response.read()).get("success", "false")
        except:
            return False

    def _error_handler(self, group: str = "") -> None:
        logger.error(f"[PushError]: group=[{group}], name: {self.name}, error message: \n{traceback.format_exc()}")

    def raw_url(self, push_conf: dict) -> str:
        if not push_conf or type(push_conf) != dict:
            return ""

        fileid = utils.trim(push_conf.get("fileid", ""))
        if not fileid:
            return ""

        return f"https://pastefy.ga/{fileid}/raw"


class PushToDrift(PushToPastefy):
    """waitting for public api"""

    def __init__(self, token: str) -> None:
        super().__init__(token=token)
        self.name = "drift"
        self.api_address = "https://paste.ding.free.hr/api/file"

    def raw_url(self, push_conf: dict) -> str:
        if not push_conf or type(push_conf) != dict:
            return ""

        fileid = push_conf.get("fileid", "")
        if utils.isblank(text=fileid):
            return ""

        return f"{self.api_address}/raw/{fileid}"

    def _is_success(self, response: HTTPResponse) -> bool:
        return response and response.getcode() in [200, 204]


class PushToImperial(PushToPastefy):
    def __init__(self, token: str) -> None:
        super().__init__(token)
        self.name = "imperial"
        self.api_address = "https://api.imperialb.in/v1/document"
        self.method = "PATCH"

    def raw_url(self, push_conf: dict) -> str:
        if not self.validate(push_conf):
            return ""

        fileid = push_conf.get("fileid", "")
        return f"https://imperialb.in/r/{fileid}"

    def _generate_payload(self, content: str, push_conf: dict) -> tuple[str, str, dict]:
        fileid = push_conf.get("fileid", "")

        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": utils.USER_AGENT,
        }

        data = json.dumps({"id": fileid, "content": content}).encode("UTF8")
        return self.api_address, data, headers


class PushToLocal(PushTo):
    def __init__(self) -> None:
        super().__init__(token="")
        self.name = "local"

    def validate(self, push_conf: dict) -> bool:
        return push_conf is not None and push_conf.get("fileid", "")

    def push_to(self, content: str, push_conf: dict, group: str = "", retry: int = 5) -> bool:
        folder = push_conf.get("folderid", "")
        filename = push_conf.get("fileid", "")
        success = self._storage(content=content, filename=filename, folder=folder)
        message = "successed" if success else "failed"
        logger.info(f"[PushInfo] push subscribes information to {self.name} {message}, group=[{group}]")
        return success

    def filter_push(self, push_conf: dict) -> dict:
        return {k: v for k, v in push_conf.items() if v.get("fileid", "")}

    def raw_url(self, push_conf: dict) -> str:
        if not push_conf or type(push_conf) != dict:
            return ""

        fileid = push_conf.get("fileid", "")
        folderid = push_conf.get("folderid", "")
        filepath = os.path.abspath(os.path.join(folderid, fileid))
        return f"{utils.FILEPATH_PROTOCAL}{filepath}"


class PushToGist(PushTo):
    def __init__(self, token: str) -> None:
        super().__init__(token=token)

        self.name = "gist"
        self.api_address = "https://api.github.com/gists"
        self.method = "PATCH"

    def validate(self, push_conf: dict) -> bool:
        if not isinstance(push_conf, dict):
            return False

        gistid = push_conf.get("gistid", "")
        filename = push_conf.get("filename", "")

        return "" != self.token.strip() and "" != gistid.strip() and "" != filename.strip()

    def _generate_payload(self, content: str, push_conf: dict) -> tuple[str, str, dict]:
        gistid = push_conf.get("gistid", "")
        filename = push_conf.get("filename", "")

        url = f"{self.api_address}/{gistid}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": utils.USER_AGENT,
        }

        data = json.dumps({"files": {filename: {"content": content, "filename": filename}}}).encode("UTF8")
        return url, data, headers

    def _is_success(self, response: HTTPResponse) -> bool:
        return response and response.getcode() == 200

    def filter_push(self, push_conf: dict) -> dict:
        if not self.token or not isinstance(push_conf, dict):
            return {}

        return {
            k: v
            for k, v in push_conf.items()
            if k and isinstance(v, dict) and v.get("gistid", "") and v.get("filename", "")
        }

    def raw_url(self, push_conf: dict) -> str:
        if not push_conf or type(push_conf) != dict:
            return ""

        username = utils.trim(push_conf.get("username", ""))
        gistid = utils.trim(push_conf.get("gistid", ""))
        revision = utils.trim(push_conf.get("revision", ""))
        filename = utils.trim(push_conf.get("filename", ""))

        if not username or not gistid or not filename:
            return ""

        prefix = f"https://gist.githubusercontent.com/{username}/{gistid}"
        if revision:
            return f"{prefix}/raw/{revision}/{filename}"

        return f"{prefix}/raw/{filename}"


ENGINE_MAPPING = {
    "imperialb.in": "imperialb",
    "gist.githubusercontent.com": "gist",
    "paste.ding.free.hr": "drift",
    "pastefy.ga": "pastefy",
    "paste.gg": "pastegg",
}

LOCAL_STORAGE = "local"

SUPPORTED_ENGINES = set(list(ENGINE_MAPPING.values()) + [LOCAL_STORAGE])


def get_instance(engine: str) -> PushTo:
    def confirm_engine(engine: str) -> str:
        engine = utils.trim(engine).lower()
        if engine and engine not in SUPPORTED_ENGINES:
            return ""

        if not engine:
            subscription = os.environ.get("SUBSCRIBE_CONF", "").strip()
            if not isurl(url=subscription):
                engine = LOCAL_STORAGE
            else:
                domain = utils.extract_domain(url=subscription, include_protocal=False)
                for k, v in ENGINE_MAPPING.items():
                    if domain == v:
                        engine = k
                        break

        return engine

    target = confirm_engine(engine=engine)
    if not target:
        raise ValueError(f"[PushError] unknown storge type: {engine}")

    token = os.environ.get("PUSH_TOKEN", "").strip()
    if target != LOCAL_STORAGE and not token:
        raise ValueError(f"[PushError] not found 'PUSH_TOKEN' in environment variables, please check it and try again")

    if target == "imperialb":
        return PushToImperial(token=token)
    elif target == "drift":
        return PushToDrift(token=token)
    elif target == "pastefy":
        return PushToPastefy(token=token)
    elif target == "pastegg":
        return PushToPasteGG(token=token)
    elif target == "gist":
        return PushToGist(token=token)

    return PushToLocal()
