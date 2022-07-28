# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import json
import os
import ssl
import traceback
import urllib
import urllib.parse
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def push_to(filepath: str, push_conf: dict, group: str, retry: int = 5) -> bool:
    folderid = push_conf.get("folderid", "")
    fileid = push_conf.get("fileid", "")
    key = push_conf.get("key", "")

    if (
        not os.path.exists(filepath)
        or not os.path.isfile(filepath)
        or "" == key.strip()
        or "" == fileid.strip()
    ):
        return False

    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    content = open(filepath, "r", encoding="utf8").read()
    data = json.dumps({"content": {"format": "text", "value": content}}).encode("UTF8")
    url = f"https://api.paste.gg/v1/pastes/{folderid}/files/{fileid}"

    try:
        request = urllib.request.Request(
            url, data=data, headers=headers, method="PATCH"
        )
        response = urllib.request.urlopen(request, context=CTX)
        if response.getcode() == 204:
            print(
                f"[PushSuccess] push subscribes information to remote successed, group=[{group}]"
            )
            return True
        else:
            print(
                "[PushError]: group=[{}], error message: \n{}".format(
                    group, response.read().decode("unicode_escape")
                )
            )
            return False

    except Exception:
        print(f"[PushError]: group=[{group}], error message:")
        traceback.print_exc()

        retry -= 1
        if retry > 0:
            return push_to(filepath, push_conf, group, retry)

        return False


def validate_push(push_configs: dict) -> dict:
    configs = {}
    for k, v in push_configs.items():
        if (
            v.get("folderid", "")
            and v.get("fileid", "")
            and v.get("key", "")
            and v.get("username", "")
        ):
            configs[k] = v

    return configs
