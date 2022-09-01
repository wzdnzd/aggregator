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


def push_file(filepath: str, push_conf: dict, group: str = "", retry: int = 5) -> bool:
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        logger.error(f"[PushError] file {filepath} not found")
        return False

    content = open(filepath, "r", encoding="utf8").read()
    return push_to(content=content, push_conf=push_conf, group=group, retry=retry)


def push_to(content: str, push_conf: dict, group: str = "", retry: int = 5) -> bool:
    if not validate(push_conf=push_conf):
        logger.error(f"[PushError] push config is invalidate")
        return False

    folderid = push_conf.get("folderid", "")
    fileid = push_conf.get("fileid", "")
    key = push_conf.get("key", "")

    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    data = json.dumps({"content": {"format": "text", "value": content}}).encode("UTF8")
    url = f"https://api.paste.gg/v1/pastes/{folderid}/files/{fileid}"

    try:
        request = urllib.request.Request(
            url, data=data, headers=headers, method="PATCH"
        )
        response = urllib.request.urlopen(request, timeout=15, context=utils.CTX)
        if response.getcode() == 204:
            logger.info(
                f"[PushSuccess] push subscribes information to remote successed, group=[{group}]"
            )
            return True
        else:
            logger.info(
                "[PushError]: group=[{}], error message: \n{}".format(
                    group, response.read().decode("unicode_escape")
                )
            )
            return False

    except Exception:
        logger.error(f"[PushError]: group=[{group}], error message:")
        traceback.print_exc()

        retry -= 1
        if retry > 0:
            return push_to(content, push_conf, group, retry)

        return False


def validate(push_conf: dict) -> bool:
    if not push_conf:
        return False

    folderid = push_conf.get("folderid", "")
    fileid = push_conf.get("fileid", "")
    key = push_conf.get("key", "")

    return "" != key.strip() and "" != folderid.strip() and "" != fileid.strip()


def filter_push(push_conf: dict) -> dict:
    configs = {}
    for k, v in push_conf.items():
        if (
            v.get("folderid", "")
            and v.get("fileid", "")
            and v.get("key", "")
            and v.get("username", "")
        ):
            configs[k] = v

    return configs
