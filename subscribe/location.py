# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-07-12

import json
import math
import os
import re
import socket
import urllib
from collections import defaultdict

import utils
from geoip2 import database
from logger import logger


def download_mmdb(repo: str, target: str, filepath: str, retry: int = 3) -> bool:
    """
    Download GeoLite2-City.mmdb from github release
    """
    repo = utils.trim(text=repo)
    if not repo or len(repo.split("/", maxsplit=1)) != 2:
        logger.error(f"invalid github repo name: {repo}")
        return False

    target = utils.trim(text=target)
    if not target:
        logger.error("invalid download target")
        return False

    # extract download url from github release page
    release_api = f"https://api.github.com/repos/{repo}/releases/latest?per_page=1"

    assets, content = None, utils.http_get(url=release_api)
    try:
        data = json.loads(content)
        assets = data.get("assets", [])
    except:
        logger.error(f"failed download {target} due to cannot extract download url through Github API")

    if not assets or not isinstance(assets, list):
        logger.error(f"no assets found for {target} in github release")
        return False

    download_url = ""
    for asset in assets:
        if asset.get("name", "") == target:
            download_url = asset.get("browser_download_url", "")
            break

    if not download_url:
        logger.error(f"no download url found for {target} in github release")
        return False

    return download(download_url, filepath, target, retry)


def download(url: str, filepath: str, filename: str, retry: int = 3) -> bool:
    """Download file from url to filepath with filename"""

    if retry < 0:
        logger.error(f"archieved max retry count for download, url: {url}")
        return False

    url = utils.trim(text=url)
    if not url:
        logger.error("invalid download url")
        return False

    filepath = utils.trim(text=filepath)
    if not filepath:
        logger.error(f"invalid save filepath, url: {url}")
        return False

    filename = utils.trim(text=filename)
    if not filename:
        logger.error(f"invalid save filename, url: {url}")
        return False

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

    logger.info(f"download file {filename} to {fullpath} success")
    return True


def load_mmdb(
    directory: str, repo: str = "alecthw/mmdb_china_ip_list", filename: str = "Country.mmdb", update: bool = False
) -> database.Reader:
    filepath = os.path.join(directory, filename)
    if update or not os.path.exists(filepath) or not os.path.isfile(filepath):
        if not download_mmdb(repo, filename, directory):
            return None

    return database.Reader(filepath)


def rename(proxy: dict, reader: database.Reader) -> dict:
    if not proxy or not isinstance(proxy, dict):
        return None

    address = utils.trim(proxy.get("server", ""))
    if not address:
        logger.warning(f"server is empty, proxy: {proxy}")
        return proxy

    try:
        ip = socket.gethostbyname(address)

        # fake ip
        if ip.startswith("198.18.0."):
            logger.warning("cannot get geolocation and rename because IP address is faked")
            return proxy

        name = proxy.get("name", "")
        response = reader.country(ip)
        country = response.country.names.get("zh-CN", "")

        if country == "中国":
            # TODO: may be a transit node, need to further confirm landing ip address
            text = re.sub(r"^[\U0001F1E6-\U0001F1FF]{2}", "", name, flags=re.I).strip()
            name = re.sub(r"(\d+|(\d+)?(-\d+)?[A-Z])$", "", text, flags=re.I).strip()
            if not name:
                name = country
        elif country:
            name = country

        proxy["name"] = name
    except Exception:
        logger.error(f"query ip geolocation failed, address: {address}")

    return proxy


def regularize(
    proxies: list[dict],
    directory: str = "",
    update: bool = False,
    num_threads: int = 0,
    show_progress: bool = True,
    locate: bool = False,
    digits: int = 2,
) -> list[dict]:
    if not proxies or not isinstance(proxies, list):
        return proxies

    if locate:
        directory = utils.trim(directory)
        if not directory:
            directory = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "data")

        # repo, filename = "PrxyHunter/GeoLite2", "GeoLite2-Country.mmdb"
        repo, filename = "alecthw/mmdb_china_ip_list", "Country.mmdb"

        # load mmdb
        reader = load_mmdb(repo=repo, directory=directory, filename=filename, update=update)
        if reader:
            tasks = [[p, reader] for p in proxies if p and isinstance(p, dict)]
            proxies = utils.multi_thread_run(rename, tasks, num_threads, show_progress, "")
        else:
            logger.error(f"skip rename proxies due to cannot load mmdb: {filename}")

    records = defaultdict(list)
    for proxy in proxies:
        name = re.sub(r"(\d+|(\d+)?(-\d+)?[A-Z])$", "", proxy.get("name", "")).strip()
        if not name:
            name = "未知地域"

        proxy["name"] = name
        records[name].append(proxy)

    results = list()
    for name, nodes in records.items():
        if not nodes:
            continue

        n = max(digits, math.floor(math.log10(len(nodes))) + 1)
        for index, node in enumerate(nodes):
            node["name"] = f"{name} {str(index+1).zfill(n)}"
            results.append(node)

    return results
