# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import os
from threading import Lock

import utils
from logger import logger

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

FILE_LOCK = Lock()

CONVERT_TARGETS = [
    "clash",
    "v2ray",
    "singbox",
    "mixed",
    "clashr",
    "quan",
    "quanx",
    "loon",
    "ss",
    "sssub",
    "ssd",
    "ssr",
    "surfboard",
    "surge",
    # "surge&ver=2",
    # "surge&ver=3",
]


def get_filename(target: str) -> str:
    target = utils.trim(target).lower()

    if target not in set(CONVERT_TARGETS):
        return ""

    if "clash" in target:
        extension = "yaml"
    elif target == "singbox":
        extension = "json"
    elif target == "v2ray" or target == "mixed":
        extension = "txt"
    else:
        extension = "conf"

    name = target.replace("&", "-").replace("=", "-")
    return f"{name}.{extension}"


def generate_conf(
    filepath: str,
    name: str,
    source: str,
    dest: str,
    target: str,
    emoji: bool = True,
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
        goal, version = "", None

        if "&" not in target:
            goal = target.strip()
        else:
            words = target.split("&", maxsplit=1)
            goal = words[0].strip()

            array = words[1].strip().split("=", maxsplit=1)
            if len(array) == 2 and utils.is_number(array[1]):
                version = int(array[1])

        if goal == "surge":
            version = max(4, version or 5)

        remove_rules = f"expand={str(not list_only).lower()}"
        lines = [name, path, url, remove_rules]
        lines.append(f"target={goal}")

        if version is not None:
            lines.append(f"ver={version}")

        if list_only:
            lines.append("list=true")
        else:
            lines.append("list=false")

        if emoji:
            lines.extend(["emoji=true", "add_emoji=true"])
        else:
            lines.extend(["emoji=false", "add_emoji=false"])

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
