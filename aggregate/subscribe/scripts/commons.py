# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-11-12

import json

import push
from logger import logger


def persist(data: dict, fileid: str, meta: str = "") -> None:
    try:
        if not fileid or data is None or type(data) != dict:
            logger.debug(
                f"[{meta}] skip persist subscibes because fileid or data is empty"
            )
            return

        pushtool = push.get_instance()
        pushtool.push_to(
            content=json.dumps(data), push_conf={"fileid": fileid}, group="subscribes"
        )
    except:
        logger.error(f"[{meta}] occur error when persist subscribes")
