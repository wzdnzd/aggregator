# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2023-06-30

import base64
import datetime
import itertools
import json
import multiprocessing
import os
import re
import sys
import time
from http.client import IncompleteRead

import push
import utils
import workflow
import yaml
from airport import AirPort
from executable import which_bin
from logger import logger

import subconverter

SUPPORT_TYPE = ["ss", "ssr", "vmess", "trojan", "snell", "http", "socks5"]


def current_date() -> str:
    timezone = datetime.timezone(datetime.timedelta(hours=8), name="Asia/Shanghai")
    now = datetime.datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(timezone)
    return str(now.date())


def detect(proxies: list, nopublic: bool, exclude: str) -> bool:
    if not nopublic or not proxies:
        return False

    exclude = utils.trim(text=exclude)
    return any(
        re.search(exclude, x.get("name", ""), flags=re.I)
        for x in proxies
        if x and type(x) == dict
    )


def fetchone(url: str, nopublic: bool = True, exclude: str = "") -> list:
    content = utils.http_get(url=url)
    if not content:
        return []

    _, subconverter = which_bin()
    try:
        proxies = AirPort.decode(text=content, program=subconverter)

        # detect if it contains shared proxy nodes
        if detect(proxies=proxies, nopublic=nopublic, exclude=exclude):
            proxies = []

        return proxies
    except:
        return []


def fetch(params: dict) -> list:
    if not params or type(params) != dict:
        return []

    domain = utils.extract_domain(params.get("url", ""), include_protocal=True)
    persist = params.get("persist", {})
    pushtool = push.get_instance()
    if not pushtool.validate(persist):
        logger.error(f"[V2RaySE] invalid persist config, please check it and try again")
        return []

    if not domain:
        domain = "https://oss.v2rayse.com"

    dates = params.get("dates", [])
    if not dates or type(dates) != list:
        dates = [current_date()]

    yamlonly = params.get("yamlonly", False)
    nopublic = params.get("nopublic", True)
    exclude = params.get("exclude", "")
    support = set(params.get("types", SUPPORT_TYPE))

    url, proxies = f"{domain}/minio/webrpc", []
    for date in dates:
        date = utils.trim(date)
        if not date:
            logger.error(f"[V2RaySE] skip crawl because date: {date} is invalid")
            continue

        payload = {
            "id": 1,
            "jsonrpc": "2.0",
            "params": {"bucketName": "proxies", "prefix": f"data/{date}/"},
            "method": "web.ListObjects",
        }
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": domain,
            "Referer": f"{domain}/minio/proxies/data/",
            "User-Agent": utils.USER_AGENT,
        }

        starttime = time.time()
        response = utils.http_post(
            url=url, headers=headers, params=payload, allow_redirects=False
        )
        status = -1 if not response else response.getcode()
        if status != 200:
            logger.error(
                f"[V2RaySE] query shared files failed, date: {date}, status code: {status}"
            )
            continue

        content, files = "", []
        try:
            try:
                content = response.read().decode("UTF8")
            except IncompleteRead:
                pass

            objects = json.loads(content).get("result", {}).get("objects", [])
            for item in objects:
                if not item or (
                    yamlonly and "text/yaml" not in item.get("contentType", "")
                ):
                    continue

                name = item.get("name", "")
                files.append([f"{domain}/proxies/{name}", nopublic, exclude])
        except:
            logger.error(
                f"[V2RaySE] parse webrpc response error, date: {date}, message: {content}"
            )

        if not files:
            logger.error(f"[V2RaySE] cannot found any valid shared file, date: {date}")
            continue

        count = min(max(1, params.get("count", sys.maxsize)), len(files))
        files = files[:count]

        cpu_count = multiprocessing.cpu_count()
        pool = multiprocessing.Pool(min(count, cpu_count * 2))
        results = pool.starmap(fetchone, files)
        nodes = [
            p
            for p in list(itertools.chain.from_iterable(results))
            if p and p.get("name", "") and p.get("type", "") in support
        ]
        proxies.extend(nodes)
        cost = "{:.2f}s".format(time.time() - starttime)
        logger.info(
            f"[V2RaySE] finished crawl for date: {date}, found {len(nodes)} proxies, cost: {cost}"
        )

    data, content = {"proxies": proxies}, " "
    datapath, artifact = subconverter.getpath(), "v2ray"
    source, dest = "proxies.yaml", "v2ray.txt"
    filepath = os.path.join(datapath, source)
    generate = os.path.join(datapath, "generate.ini")

    with open(filepath, "w+", encoding="utf8") as f:
        yaml.dump(data, f, allow_unicode=True)

    if os.path.exists(generate) and os.path.isfile(generate):
        os.remove(generate)

    success = subconverter.generate_conf(generate, artifact, source, dest, "mixed")
    if not success:
        logger.error(f"[V2raySE] cannot generate subconverter config file")
        content = yaml.dump(data=data, allow_unicode=True)
    else:
        _, program = which_bin()
        if subconverter.convert(binname=program, artifact=artifact):
            filepath = os.path.join(datapath, dest)
            if not os.path.exists(filepath) or not os.path.isfile(filepath):
                logger.error(f"[V2raySE] converted file {filepath} not found")
                return []

            with open(filepath, "r", encoding="utf8") as f:
                content = f.read()
            if not utils.isb64encode(content=content):
                try:
                    content = base64.b64encode(content.encode(encoding="UTF8")).decode(
                        encoding="UTF8"
                    )
                except Exception as e:
                    logger.error(
                        f"[V2raySE] base64 encode converted data error, message: {str(e)}"
                    )
                    return []

        # clean workspace
        workflow.cleanup(datapath, filenames=[source, dest, "generate.ini"])

    success = pushtool.push_to(content=content, push_conf=persist, group="v2rayse")
    if not success:
        logger.error(f"[V2RaySE] failed to storage {len(proxies)} proxies")
        return []

    config = params.get("config", {})
    config["sub"] = pushtool.raw_url(push_conf=persist)
    config["saved"] = True
    config["name"] = "v2rayse" if not config.get("name", "") else config.get("name")
    config["push_to"] = list(set(config.get("push_to", [])))
    return [config]
