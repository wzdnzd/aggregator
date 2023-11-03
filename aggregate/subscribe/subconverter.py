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
        only_proxies = "list=true"
        remove_rules = "expand=false"
        lines = [name, path, target, url, only_proxies, remove_rules]

        if ignore_exclude:
            lines.append(f"exclude=流量|过期|剩余|时间|Expire|Traffic")

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

    return utils.cmd(args)


def getpath() -> str:
    return os.path.join(PATH, "subconverter")
