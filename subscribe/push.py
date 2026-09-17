# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import json
import os
import traceback
import urllib
import urllib.request
from http.client import HTTPResponse

import utils
from config.models import StorageConfig, StorageItem
from logger import logger
from urlvalidator import isurl

LOCAL_STORAGE = "local"


class PushTo(object):
    def __init__(self, token: str = "", base: str = "", domain: str = "") -> None:
        base, domain = utils.trim(base), utils.trim(domain)
        if base and not domain:
            domain = base
        elif not base and domain:
            base = domain

        self.name = ""
        self.method = "PUT"
        self.domain = domain
        self.api_address = base
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

    def push_file(self, filepath: str, item: StorageItem, group: str = "", retry: int = 5) -> bool:
        if not os.path.exists(filepath) or not os.path.isfile(filepath):
            logger.error(f"[PushFileError] file {filepath} not found")
            return False

        content = " "
        with open(filepath, "r", encoding="utf8") as f:
            content = f.read()

        return self.push_to(content=content, item=item, group=group, retry=retry)

    def push_to(self, content: str, item: StorageItem, group: str = "", retry: int = 5, **kwargs: object) -> bool:
        if not self.validate(item=item):
            logger.error(f"[PushError] push config is invalidate, domain: {self.name}")
            return False

        if item.local:
            self._storage(content=content, filename=item.local)

        url, data, headers = self._generate_payload(content=content, item=item)
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

        except Exception as e:
            try:
                if isinstance(e, urllib.error.HTTPError):
                    code = getattr(e, "code", None)
                    try:
                        message = e.read().decode("utf-8", errors="replace")
                    except Exception:
                        message = "cannot read error messgae from response"
                    logger.error(
                        f"[PushError] request failed, code: {code}, url: {url}, message: {message}, data: {data}"
                    )
            except Exception:
                logger.error(f"[PushError] failed to process exception: {traceback.format_exc()}")

            self._error_handler(group=group)

            retry -= 1
            if retry > 0:
                return self.push_to(content, item, group, retry)

            return False

    def _is_success(self, response: HTTPResponse) -> bool:
        return response and response.getcode() == 200

    def _generate_payload(self, content: str, item: StorageItem) -> tuple[str, str, dict]:
        raise NotImplementedError

    def _error_handler(self, group: str = "") -> None:
        logger.error(f"[PushError]: group=[{group}], name: {self.name}, error message: \n{traceback.format_exc()}")

    def validate(self, item: StorageItem) -> bool:
        raise NotImplementedError

    def filter_push(self, items: dict[str, StorageItem]) -> dict[str, StorageItem]:
        raise NotImplementedError

    def raw_url(self, item: StorageItem) -> str:
        raise NotImplementedError


class PushToPasteGG(PushTo):
    """https://paste.gg"""

    def __init__(self, token: str, base: str = "", domain: str = "") -> None:
        base = utils.trim(base).removesuffix("/") or "https://api.paste.gg"
        if not isurl(base):
            raise ValueError(f"[PushError] invalid base address for pastegg: {base}")

        domain = utils.trim(domain).removesuffix("/") or "https://paste.gg"
        if not isurl(domain):
            raise ValueError(f"[PushError] invalid domain address for pastegg: {domain}")

        super().__init__(token=token, base=base, domain=domain)

        self.name = "pastegg"
        self.method = "PATCH"
        self.domain = domain
        self.api_address = f"{base}/v1/pastes"

    def validate(self, item: StorageItem) -> bool:
        if not isinstance(item, StorageItem):
            return False

        folder_id = item.folder_id
        file_id = item.file_id

        return "" != self.token.strip() and "" != folder_id.strip() and "" != file_id.strip()

    def _generate_payload(self, content: str, item: StorageItem) -> tuple[str, str, dict]:
        folder_id = item.folder_id
        file_id = item.file_id

        headers = {
            "Authorization": f"Key {self.token}",
            "Content-Type": "application/json",
            "User-Agent": utils.USER_AGENT,
        }
        data = json.dumps({"content": {"format": "text", "value": content}}).encode("UTF8")
        url = f"{self.api_address}/{folder_id}/files/{file_id}"

        return url, data, headers

    def _is_success(self, response: HTTPResponse) -> bool:
        return response and response.getcode() == 204

    def _error_handler(self, group: str = "") -> None:
        logger.error(f"[PushError]: group=[{group}], name: {self.name}, error message: \n{traceback.format_exc()}")

    def filter_push(self, items: dict[str, StorageItem]) -> dict[str, StorageItem]:
        records = {}
        for k, v in items.items():
            if self.token and v.folder_id and v.file_id and v.username:
                records[k] = v

        return records

    def raw_url(self, item: StorageItem) -> str:
        if not isinstance(item, StorageItem):
            return ""

        file_id = item.file_id
        folder_id = item.folder_id
        username = item.username

        if not file_id or not folder_id or not username:
            return ""

        return f"{self.domain}/p/{username}/{folder_id}/files/{file_id}/raw"


class PushToDevbin(PushToPasteGG):
    """https://devbin.dev"""

    def __init__(self, token: str, base: str = "") -> None:
        base = utils.trim(base).removesuffix("/") or "https://devbin.dev"
        if not isurl(base):
            raise ValueError(f"[PushError] invalid base address for devbin: {base}")

        super().__init__(token=token, base=base)

        self.name = "devbin"
        self.domain = base
        self.api_address = f"{base}/api/v3/paste"

    def validate(self, item: StorageItem) -> bool:
        if not isinstance(item, StorageItem):
            return False

        file_id = item.file_id
        return "" != self.token.strip() and "" != file_id.strip()

    def filter_push(self, items: dict[str, StorageItem]) -> dict[str, StorageItem]:
        records = {}
        for k, v in items.items():
            if v.file_id and self.token:
                records[k] = v

        return records

    def _generate_payload(self, content: str, item: StorageItem) -> tuple[str, str, dict]:
        file_id = item.file_id

        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "Accept": "*/*",
        }
        data = json.dumps({"content": content, "syntaxName": "auto"}).encode("UTF8")
        url = f"{self.api_address}/{file_id}"

        return url, data, headers

    def _is_success(self, response: HTTPResponse) -> bool:
        return response and response.getcode() == 201

    def raw_url(self, item: StorageItem) -> str:
        if not isinstance(item, StorageItem) or not item.file_id:
            return ""

        file_id = item.file_id
        return f"{self.domain}/Raw/{file_id}"


class PushToPastefy(PushToDevbin):
    """https://pastefy.app"""

    def __init__(self, token: str, base: str = "") -> None:
        base = utils.trim(base).removesuffix("/") or "https://pastefy.app"
        if not isurl(base):
            raise ValueError(f"[PushError] invalid base address for pastefy: {base}")

        super().__init__(token=token, base=base)

        self.name = "pastefy"
        self.method = "PUT"
        self.domain = base
        self.api_address = f"{base}/api/v2/paste"

    def _generate_payload(self, content: str, item: StorageItem) -> tuple[str, str, dict]:
        file_id = item.file_id

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": utils.USER_AGENT,
        }
        data = json.dumps({"content": content}).encode("UTF8")
        url = f"{self.api_address}/{file_id}"

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

    def raw_url(self, item: StorageItem) -> str:
        if not isinstance(item, StorageItem):
            return ""

        file_id = utils.trim(item.file_id)
        if not file_id:
            return ""

        return f"{self.domain}/{file_id}/raw"


class PushToImperial(PushToPasteGG):
    """https://imperialb.in"""

    def __init__(self, token: str, base: str = "", domain: str = "") -> None:
        base = utils.trim(base).removesuffix("/") or "https://api.imperialb.in"
        if not isurl(base):
            raise ValueError(f"[PushError] invalid base address for imperial: {base}")

        domain = utils.trim(domain).removesuffix("/") or "https://imperialb.in"
        if not isurl(domain):
            raise ValueError(f"[PushError] invalid domain address for imperial: {domain}")

        super().__init__(token=token, base=base, domain=domain)

        self.name = "imperial"
        self.method = "PATCH"
        self.domain = domain
        self.api_address = f"{base}/v1/document"

    def raw_url(self, item: StorageItem) -> str:
        if not self.validate(item):
            return ""

        file_id = item.file_id
        return f"{self.domain}/r/{file_id}"

    def validate(self, item: StorageItem) -> bool:
        if not isinstance(item, StorageItem):
            return False

        file_id = item.file_id
        return "" != self.token.strip() and "" != file_id.strip()

    def filter_push(self, items: dict[str, StorageItem]) -> dict[str, StorageItem]:
        records = {}
        for k, v in items.items():
            if v.file_id and self.token:
                records[k] = v

        return records

    def _generate_payload(self, content: str, item: StorageItem) -> tuple[str, str, dict]:
        file_id = item.file_id

        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": utils.USER_AGENT,
        }

        data = json.dumps({"id": file_id, "content": content}).encode("UTF8")
        return self.api_address, data, headers

    def _is_success(self, response: HTTPResponse) -> bool:
        if not response or response.getcode() != 200:
            return False

        try:
            return json.loads(response.read()).get("success", "false")
        except:
            return False


class PushToLocal(PushTo):
    def __init__(self) -> None:
        super().__init__(token="")
        self.name = "local"

    def validate(self, item: StorageItem) -> bool:
        return isinstance(item, StorageItem) and bool(item.file_id)

    def push_to(self, content: str, item: StorageItem, group: str = "", retry: int = 5) -> bool:
        folder = item.folder_id
        filename = item.file_id
        success = self._storage(content=content, filename=filename, folder=folder)
        message = "successed" if success else "failed"
        logger.info(f"[PushInfo] push subscribes information to {self.name} {message}, group=[{group}]")
        return success

    def filter_push(self, items: dict[str, StorageItem]) -> dict[str, StorageItem]:
        return {k: v for k, v in items.items() if isinstance(v, StorageItem) and v.file_id}

    def raw_url(self, item: StorageItem) -> str:
        if not isinstance(item, StorageItem):
            return ""

        file_id = item.file_id
        folder_id = item.folder_id
        filepath = os.path.abspath(os.path.join(folder_id, file_id))
        return f"{utils.FILEPATH_PROTOCAL}{filepath}"


class PushToGist(PushTo):
    def __init__(self, token: str) -> None:
        super().__init__(token=token)

        self.name = "gist"
        self.api_address = "https://api.github.com/gists"
        self.domain = "https://gist.githubusercontent.com"
        self.method = "PATCH"

    def validate(self, item: StorageItem) -> bool:
        if not isinstance(item, StorageItem):
            return False

        gist_id = item.gist_id
        filename = item.filename

        return "" != self.token.strip() and "" != gist_id.strip() and "" != filename.strip()

    def _generate_payload(self, content: str, item: StorageItem) -> tuple[str, str, dict]:
        gist_id = item.gist_id
        filename = item.filename

        url = f"{self.api_address}/{gist_id}"
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

    def filter_push(self, items: dict[str, StorageItem]) -> dict[str, StorageItem]:
        if not self.token or not isinstance(items, dict):
            return {}

        return {k: v for k, v in items.items() if k and isinstance(v, StorageItem) and v.gist_id and v.filename}

    def raw_url(self, item: StorageItem) -> str:
        if not isinstance(item, StorageItem):
            return ""

        username = utils.trim(item.username)
        gist_id = utils.trim(item.gist_id)
        revision = utils.trim(item.revision)
        filename = utils.trim(item.filename)

        if not username or not gist_id or not filename:
            return ""

        prefix = f"{self.domain}/{username}/{gist_id}"
        if revision:
            return f"{prefix}/raw/{revision}/{filename}"

        return f"{prefix}/raw/{filename}"


class PushToQBin(PushToPastefy):
    """https://qbin.me"""

    def __init__(self, token: str, base: str = "") -> None:
        base = utils.trim(base).removesuffix("/") or "https://qbin.me"
        if not isurl(base):
            raise ValueError(f"[PushError] invalid base address for qbin: {base}")

        super().__init__(token=token, base=base)

        self.name = "qbin"
        self.method = "POST"
        self.domain = base
        self.api_address = f"{base}/save"

    def validate(self, item: StorageItem) -> bool:
        if not isinstance(item, StorageItem):
            return False

        file_id = item.file_id
        return "" != self.token.strip() and "" != utils.trim(file_id)

    def _generate_payload(self, content: str, item: StorageItem) -> tuple[str, str, dict]:
        file_id = item.file_id
        password = item.password
        expire = item.expire

        headers = {
            "Cookie": f"token={self.token}",
            "Content-Type": "text/plain; charset=UTF-8",
            "User-Agent": utils.USER_AGENT,
        }

        if isinstance(expire, int) and expire > 0:
            headers["x-expire"] = str(expire)

        url = f"{self.api_address}/{file_id}"
        if password:
            url = f"{url}/{password}"

        return url, content.encode("UTF-8"), headers

    def _is_success(self, response: HTTPResponse) -> bool:
        if not response or response.getcode() != 200:
            return False

        try:
            result = json.loads(response.read())
            return result.get("status", 403) == 200
        except:
            return False

    def filter_push(self, items: dict[str, StorageItem]) -> dict[str, StorageItem]:
        records = {}
        for k, v in items.items():
            if v.file_id and self.token:
                records[k] = v

        return records

    def raw_url(self, item: StorageItem) -> str:
        if not isinstance(item, StorageItem):
            return ""

        file_id = utils.trim(item.file_id)
        password = utils.trim(item.password)

        if not file_id:
            return ""

        url = f"{self.domain}/r/{file_id}"
        if password:
            url = f"{url}/{password}"

        return url


SUPPORTED_ENGINES = set(["gist", "imperial", "pastefy", "pastegg", "qbin"] + [LOCAL_STORAGE])


def get_instance(storage: StorageConfig) -> PushTo:
    if not isinstance(storage, StorageConfig):
        raise ValueError("[PushError] invalid storage config")

    engine = utils.trim(storage.engine)
    if engine not in SUPPORTED_ENGINES:
        raise ValueError(f"[PushError] unknown storge type: {engine}")

    token = utils.trim(storage.token or os.environ.get("PUSH_TOKEN", ""))
    if engine != LOCAL_STORAGE and not token:
        raise ValueError("[PushError] not found 'PUSH_TOKEN' in environment variables, please check it and try again")

    if engine == "gist":
        return PushToGist(token=token)

    base, domain = utils.trim(storage.base), utils.trim(storage.domain)
    if engine == "imperial":
        return PushToImperial(token=token, base=base, domain=domain)
    elif engine == "pastefy":
        return PushToPastefy(token=token, base=base or domain)
    elif engine == "pastegg":
        return PushToPasteGG(token=token, base=base, domain=domain)
    elif engine == "qbin":
        return PushToQBin(token=token, base=base or domain)

    return PushToLocal()
