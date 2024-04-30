# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import os
from threading import Lock

import utils
from logger import logger

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

FILE_LOCK = Lock()


def generate_conf(
    filepath: str,
    name: str,
    source: str,
    dest: str,
    target: str,
    list_only: bool = True,
    ignore_exclude: bool = False,
) -> None:
    if not filepath or not name or not source or not dest or not target:
        logger.error("invalidate arguments, so cannot execute subconverter")
        return False

    try:
        name = f"[{name.strip()}]"
        path = f"path={dest.strip()}"
        url = f"url={source.strip()}"
        target = f"target={target.strip()}"
        remove_rules = f"expand={str(not list_only).lower()}"
        lines = [name, path, target, url, remove_rules]

        if list_only:
            lines.append("list=true")

        if ignore_exclude:
            lines.append("exclude=流量|过期|剩余|时间|Expire|Traffic")

        lines.append("\n")
        content = "\n".join(lines)

        FILE_LOCK.acquire(30)
        try:
            with open(filepath, "a+", encoding="utf8") as f:
                f.write(content)
                f.flush()
        finally:
            FILE_LOCK.release()

        return True
    except:
        return False


def convert(binname: str, artifact: str = "") -> bool:
    binpath = os.path.join(PATH, "subconverter", binname)
    utils.chmod(binpath)
    args = [binpath, "-g"]
    if artifact is not None and "" != artifact:
        args.append("--artifact")
        args.append(artifact)

    success, _ = utils.cmd(args)
    return success


def getpath() -> str:
    return os.path.join(PATH, "subconverter")
