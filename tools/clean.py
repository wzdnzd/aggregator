# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-07-09


import argparse
import gzip
import json
import math
import os
import random
import re
import socket
import ssl
import string
import typing
import urllib
import urllib.request
from collections import defaultdict
from http.client import HTTPResponse

import yaml
from geoip2 import database

PATH = os.path.abspath(os.path.dirname(__file__))

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


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


def download_mmdb(repo: str, target: str, filepath: str, retry: int = 3):
    """
    Download GeoLite2-City.mmdb from github release
    """
    repo = trim(text=repo)
    if not repo or len(repo.split("/", maxsplit=1)) != 2:
        raise ValueError(f"invalid github repo name: {repo}")

    target = trim(target)
    if not target:
        raise ValueError("invalid download target")

    # extract download url from github release page
    release_api = f"https://api.github.com/repos/{repo}/releases/latest?per_page=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    }

    count, response = 0, None
    while count < retry and response is None:
        try:
            request = urllib.request.Request(url=release_api, headers=headers)
            response = urllib.request.urlopen(request, timeout=10, context=CTX)
        except Exception:
            count += 1

    assets = read_response(response=response, expected=200, deserialize=True, key="assets")
    if not assets or not isinstance(assets, list):
        raise Exception("no assets found in github release")

    download_url = ""
    for asset in assets:
        if asset.get("name", "") == target:
            download_url = asset.get("browser_download_url", "")
            break

    if not download_url:
        raise Exception("no download url found in github release")

    download(download_url, filepath, target, retry)


def download(url: str, filepath: str, filename: str, retry: int = 3) -> None:
    """Download file from url to filepath with filename"""

    if retry < 0:
        raise Exception("archieved max retry count for download")

    url = trim(url)
    if not url:
        raise ValueError("invalid download url")

    filepath = trim(filepath)
    if not filepath:
        raise ValueError("invalid save filepath")

    filename = trim(filename)
    if not filename:
        raise ValueError("invalid save filename")

    if not os.path.exists(filepath) or not os.path.isdir(filepath):
        os.makedirs(filepath)

    fullpath = os.path.join(filepath, filename)
    if os.path.exists(fullpath) and os.path.isfile(fullpath):
        os.remove(fullpath)

    # download target file from github release to fullpath
    try:
        urllib.request.urlretrieve(url=url, filename=fullpath)
    except Exception:
        return download(url, filepath, filename, retry - 1)

    print(f"download file {filename} to {fullpath} success")


def load_mmdb(
    directory: str, repo: str = "alecthw/mmdb_china_ip_list", filename: str = "Country.mmdb", update: bool = False
) -> database.Reader:
    filepath = os.path.join(directory, filename)
    if update or not os.path.exists(filepath) or not os.path.isfile(filepath):
        if not download_mmdb(repo, filename, directory):
            return None

    return database.Reader(filepath)


def read_response(response: HTTPResponse, expected: int = 200, deserialize: bool = False, key: str = "") -> typing.Any:
    if not response or not isinstance(response, HTTPResponse):
        return None

    success = expected <= 0 or expected == response.getcode()
    if not success:
        return None

    try:
        text = response.read()
    except:
        text = b""

    try:
        content = text.decode(encoding="UTF8")
    except UnicodeDecodeError:
        content = gzip.decompress(text).decode("UTF8")
    except:
        content = ""

    if not deserialize:
        return content

    if not content:
        return None
    try:
        data = json.loads(content)
        return data if not key else data.get(key, None)
    except:
        return None


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
            f.seek(0, 0)
            yaml.add_multi_constructor("str", lambda loader, suffix, node: str(node.value), Loader=yaml.SafeLoader)
            nodes = yaml.load(f, Loader=yaml.SafeLoader).get("proxies", [])
        except:
            nodes = []

        if nodes and args.location:
            workspace = os.path.abspath(trim(args.workspace) or PATH)
            reader = load_mmdb(directory=workspace, update=args.update)
        else:
            reader = None

        records = set()
        for item in nodes:
            if not item or not isinstance(item, dict):
                continue

            server = item.get("server", "")
            port = item.get("port", "")
            key = f"{server}:{port}"

            if key not in records:
                records.add(key)

                if reader:
                    address = trim(item.get("server", ""))
                    if not address:
                        continue

                    try:
                        ip = socket.gethostbyname(address)

                        # fake ip
                        if not ip.startswith("198.18.0."):
                            name = item.get("name", "")
                            response = reader.country(ip)
                            country = response.country.names.get("zh-CN", "")

                            if country == "中国":
                                # TODO: may be a transit node, need to further confirm landing ip address
                                name = re.sub(r"^[\U0001F1E6-\U0001F1FF]{2}", "", name, flags=re.I)
                            elif country:
                                name = country
                        else:
                            print("cannot get geolocation and rename because IP address is faked")

                        item["name"] = name
                    except Exception:
                        pass

                name = re.sub(r"(\d+|(\d+)?(-\d+)?[A-Z])$", "", item.get("name", "")).strip()
                if not name:
                    name = "".join(random.sample(string.ascii_uppercase, 6))

                item["name"] = name

                if args.secure:
                    if "tls" in item:
                        item["tls"] = True
                    if "skip-cert-verify" in item:
                        item["skip-cert-verify"] = False

                caches[name].append(item)

    proxies = list()
    for name, nodes in caches.items():
        n = max(args.num, math.floor(math.log10(len(nodes))) + 1)

        for index, node in enumerate(nodes):
            node["name"] = f"{name} {str(index+1).zfill(n)}"
            proxies.append(node)

    if not proxies:
        print(f"no proxies found in file {filepath}")
        return

    data = {"proxies": proxies}
    if args.backup:
        copy(filepath)
    with open(filepath, "w+", encoding="utf8") as f:
        yaml.dump(data, f, allow_unicode=True)

    print(f"process finished, file has been saved to {filepath}")


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

    parser.add_argument(
        "-l",
        "--location",
        dest="location",
        action="store_true",
        default=False,
        help="Modify proxy name to country corresponding to the IP or domain",
    )

    parser.add_argument(
        "-n",
        "--num",
        type=int,
        required=False,
        default=2,
        help="Number of digits to fill",
    )

    parser.add_argument(
        "-s",
        "--secure",
        dest="secure",
        action="store_true",
        default=False,
        help="Enforce TLS and reject skipping certificate validation",
    )

    parser.add_argument(
        "-u",
        "--update",
        dest="update",
        action="store_true",
        default=False,
        help="force update geoip database",
    )

    parser.add_argument(
        "-w",
        "--workspace",
        type=str,
        default=PATH,
        required=False,
        help="workspace absolute path",
    )

    main(parser.parse_args())
