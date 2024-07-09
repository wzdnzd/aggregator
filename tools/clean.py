# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-07-09


import argparse
import os
import re
from collections import defaultdict

import yaml


def trim(text: str) -> str:
    if not text or type(text) != str:
        return ""

    return text.strip()


def copy(filepath: str) -> None:
    if not filepath or not os.path.exists(filepath) or not os.path.isfile(filepath):
        return

    newfile = f"{filepath}.bak"
    if os.path.exists(newfile):
        os.remove(newfile)

    os.rename(filepath, newfile)


def main(args: argparse.Namespace) -> None:
    filepath = os.path.abspath(trim(args.config))
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        print(f"file {filepath} not exists")
        return

    caches = defaultdict(list)
    with open(filepath, "r", encoding="utf8") as f:
        try:
            nodes = yaml.load(f, Loader=yaml.SafeLoader).get("proxies", [])
        except yaml.constructor.ConstructorError:
            yaml.add_multi_constructor("str", lambda loader, suffix, node: None, Loader=yaml.SafeLoader)
            nodes = yaml.load(f, Loader=yaml.FullLoader).get("proxies", [])
        except:
            nodes = []

        records = set()
        for item in nodes:
            if not item or not isinstance(item, dict):
                continue

            server = item.get("server", "")
            port = item.get("port", "")
            key = f"{server}:{port}"

            if key not in records:
                records.add(key)

                name = re.sub(r"\d+", "", item.get("name", "")).strip()
                item["name"] = name
                caches[name].append(item)

    proxies = list()
    for name, nodes in caches.items():
        for index, node in enumerate(nodes):
            node["name"] = f"{name} {str(index+1).zfill(2)}"
            proxies.append(node)

    if not proxies:
        print(f"no proxies found in file {filepath}")
        return

    data = {"proxies": proxies}
    if args.backup:
        copy(filepath)
    with open(filepath, "w+", encoding="utf8") as f:
        yaml.dump(data, f, allow_unicode=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-b",
        "--backup",
        dest="backup",
        action="store_true",
        default=False,
        help="Backup old provider file",
    )

    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default="config.yaml",
        required=False,
        help="Clash configuration filename",
    )

    main(parser.parse_args())
