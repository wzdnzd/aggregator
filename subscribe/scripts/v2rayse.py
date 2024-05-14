# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2023-06-30

import base64
import json
import os
import re
import sys
import time
import traceback
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from http.client import IncompleteRead

import push
import utils
import workflow
import yaml
from airport import AirPort
from crawl import naming_task
from executable import which_bin
from logger import logger
from origin import Origin

import subconverter

# outbind type
SUPPORT_TYPE = ["ss", "ssr", "vmess", "trojan", "snell", "vless", "hysteria2", "hysteria", "http", "socks5"]

# date format
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# last modified key name
LAST_MODIFIED = "lastModified"

# whether enable special protocols
SPECIAL_PROTOCOLS = AirPort.enable_special_protocols()


def current_time(utc: bool = True) -> datetime:
    now = datetime.utcnow()
    if not utc:
        tz = timezone(timedelta(hours=8), name="Asia/Shanghai")
        now = now.replace(tzinfo=tz.utc).astimezone(tz)

    return now


def get_dates(last: datetime) -> list[str]:
    last, dates = last if last else current_time(utc=True), []

    # change timezone to Asia/Shanghai
    # tz = timezone(timedelta(hours=8), name="Asia/Shanghai")
    # start = (last.replace(tzinfo=tz.utc).astimezone(tz).replace(hour=0, minute=0, second=0))
    # end = current_time(utc=False).replace(hour=23, minute=59, second=59)

    start = last.replace(hour=0, minute=0, second=0)
    end = current_time(utc=True).replace(hour=23, minute=59, second=59)

    while start <= end:
        dates.append(start.strftime("%Y-%m-%d"))
        start += timedelta(days=1)

    return dates


def detect(proxies: list, nopublic: bool, exclude: str, ignore: str, repeat: int) -> bool:
    exclude = utils.trim(text=exclude)
    ignore = utils.trim(text=ignore)
    repeat = max(1, repeat)

    if not nopublic or not proxies or not exclude:
        return False

    count = 0
    for p in proxies:
        if not p or type(p) != dict:
            continue

        name = str(p.get("name", ""))
        try:
            if ignore and re.search(ignore, name, flags=re.I):
                continue

            if re.search(exclude, name, flags=re.I):
                count += 1
        except:
            logger.error(
                f"[V2RaySE] invalid regex, ignore: {ignore}, exclude: {exclude}, message: \n{traceback.format_exc()}"
            )

        if count >= repeat:
            return True

    return False


def last_history(url: str, interval: int = 12) -> datetime:
    last = current_time(utc=True) + timedelta(hours=-abs(int(interval)))
    content = utils.http_get(url=url)
    if content:
        modified = ""
        try:
            modified = json.loads(content).get(LAST_MODIFIED, "")
            if modified:
                last = datetime.strptime(modified, DATE_FORMAT) + timedelta(minutes=-10)
        except Exception:
            logger.error(f"[V2RaySE] invalid date format: {modified}")

    return last


def fetchone(
    url: str,
    nopublic: bool = True,
    exclude: str = "",
    ignore: str = "",
    repeat: int = 1,
    noproxies: bool = False,
) -> tuple[list, list]:
    content = utils.http_get(url=url)
    if not content:
        return [], []

    _, subconverter = which_bin()
    proxies, subscriptions = [], []

    if not utils.isb64encode(content=content):
        regex = r"(?:https?://)?(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+(?:(?:(?:/index.php)?/api/v1/client/subscribe\?token=[a-zA-Z0-9]{16,32})|(?:/link/[a-zA-Z0-9]+\?(?:sub|mu|clash)=\d))"
        groups = re.findall(regex, content, flags=re.I)
        if groups:
            subscriptions = list(set([utils.url_complete(x) for x in groups if x]))

    if not noproxies:
        try:
            proxies = AirPort.decode(text=content, program=subconverter, special=SPECIAL_PROTOCOLS, throw=True)

            # detect if it contains shared proxy nodes
            if detect(
                proxies=proxies,
                nopublic=nopublic,
                exclude=exclude,
                ignore=ignore,
                repeat=repeat,
            ):
                proxies = []
            elif url.endswith(".json"):
                try:
                    outbounds = json.loads(content).get("outbounds", [])
                    for outbound in outbounds:
                        if outbound.get("type", "") == "tuic":
                            logger.info(f"[V2RaySE] found tuic outbound in url: {url}")
                            break
                except:
                    pass
        except:
            logger.error(f"[V2RaySE] parse proxies failed, url: {url}, message: \n{traceback.format_exc()}")

    return proxies, subscriptions


def fetch(params: dict) -> list:
    if not params or type(params) != dict:
        return []

    domain = utils.extract_domain(params.get("url", ""), include_protocal=True)
    if not domain:
        logger.error(f"[V2RaySE] skip collect data due to parameter 'url' missing")
        return []

    persist = params.get("persist", {})
    pushtool = push.get_instance()
    if not persist or type(persist) != dict or not pushtool.validate(persist.get("proxies", {})):
        logger.error(f"[V2RaySE] invalid persist config, please check it and try again")
        return []

    filetype = int(params.get("source", 0))
    nopublic = params.get("nopublic", True)
    exclude = params.get("exclude", "")
    ignore = params.get("ignore", "")
    support = set(params.get("types", SUPPORT_TYPE))
    interval = max(1, int(params.get("interval", 12)))
    repeat = max(1, int(params.get("repeat", 1)))
    noproxies = params.get("noproxies", False) == True
    maxsize = min(max(524288, int(params.get("maxsize", 524288))), sys.maxsize)

    # storage config
    proxies_store = persist.get("proxies", {})
    modified_store = persist.get("modified", {})

    history_url = pushtool.raw_url(push_conf=modified_store)
    last = last_history(url=history_url, interval=interval)

    dates, manual = params.get("dates", []), True
    if not dates or type(dates) != list:
        dates, manual = get_dates(last=last), False

    begin = current_time(utc=True).strftime(DATE_FORMAT)
    if manual:
        last = time.strptime("1970-01-01 00:00:00", DATE_FORMAT)
        logger.info(f"[V2RaySE] begin crawl data, dates: {dates}")
    else:
        logger.info(f"[V2RaySE] begin crawl data from [{last.strftime(DATE_FORMAT)}] to [{begin}]")

    url, tasks = f"{domain}/minio/webrpc", []
    proxies, subscriptions = [], set()

    for date in sorted(list(set(dates)), reverse=True):
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
        response = utils.http_post(url=url, headers=headers, params=payload, allow_redirects=False)
        status = -1 if not response else response.getcode()
        if status != 200:
            logger.error(f"[V2RaySE] query shared files failed, date: {date}, status code: {status}")
            continue

        content, files = "", []
        try:
            try:
                content = response.read().decode("UTF8")
            except IncompleteRead:
                pass

            objects = json.loads(content).get("result", {}).get("objects", [])
            if objects is None:
                logger.error(f"[V2RaySE] folder {date} not exists")
                continue

            for item in objects:
                # filter by content type
                if (
                    not item
                    or (filetype == 1 and "text/yaml" not in item.get("contentType", ""))
                    or (filetype == 2 and "text/json" not in item.get("contentType", ""))
                ):
                    continue

                # filter by size and last modified time
                if "size" in item and item.get("size", 0) > maxsize:
                    continue

                if "lastModified" in item:
                    try:
                        modified = datetime.fromisoformat(item.get("lastModified", "")[:-1])
                        if modified < last:
                            continue
                    except:
                        pass

                name = item.get("name", "")
                files.append(
                    [
                        f"{domain}/proxies/{name}",
                        nopublic,
                        exclude,
                        ignore,
                        repeat,
                        noproxies,
                    ]
                )
        except:
            logger.error(f"[V2RaySE] parse webrpc response error, date: {date}, message: {content}")

        if not files:
            logger.error(f"[V2RaySE] cannot found any valid shared file, date: {date}")
            continue

        count = min(max(1, params.get("count", sys.maxsize)), len(files))
        files = files[:count]
        results = utils.multi_process_run(func=fetchone, tasks=files)

        nodes, subs, count = [], [], 0
        for result in results:
            nodes.extend([p for p in result[0] if p and p.get("name", "") and p.get("type", "") in support])
            subs.extend([x for x in result[1] if x])

        proxies.extend(nodes)
        if len(subs) > 0:
            urls = set(subs)
            count = len(urls)
            subscriptions = subscriptions.union(urls)

        cost = "{:.2f}s".format(time.time() - starttime)
        logger.info(
            f"[V2RaySE] finished crawl for date: {date}, found {len(nodes)} proxies and {count} subscriptions, cost: {cost}"
        )

    logger.info(
        f"[V2RaySE] finished all crawl tasks, found {len(proxies)} proxies and {len(subscriptions)} subscriptions: {list(subscriptions)}"
    )

    for sub in subscriptions:
        config = deepcopy(params.get("config", {}))
        config["sub"] = sub
        config["checked"] = False
        config["saved"] = False
        config["origin"] = Origin.V2RAYSE.name
        config["name"] = naming_task(sub)
        config["push_to"] = list(set(config.get("push_to", [])))

        tasks.append(config)

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
        logger.error(f"[V2RaySE] cannot generate subconverter config file")
        content = yaml.dump(data=data, allow_unicode=True)
    else:
        _, program = which_bin()
        if subconverter.convert(binname=program, artifact=artifact):
            filepath = os.path.join(datapath, dest)
            if not os.path.exists(filepath) or not os.path.isfile(filepath):
                logger.error(f"[V2RaySE] converted file {filepath} not found")
                return tasks

            with open(filepath, "r", encoding="utf8") as f:
                content = f.read()
            if not utils.isb64encode(content=content):
                try:
                    content = base64.b64encode(content.encode(encoding="UTF8")).decode(encoding="UTF8")
                except Exception as e:
                    logger.error(f"[V2RaySE] base64 encode converted data error, message: {str(e)}")
                    return tasks

        # clean workspace
        workflow.cleanup(datapath, filenames=[source, dest, "generate.ini"])

    success = pushtool.push_to(content=content, push_conf=proxies_store, group="v2rayse")
    if not success:
        filename = os.path.join(os.path.dirname(datapath), "data", "v2rayse.txt")
        logger.error(f"[V2RaySE] failed to storage {len(proxies)} proxies, will save it to local file {filename}")

        utils.write_file(filename=filename, lines=content)
        return tasks

    # save last modified time
    if not manual and pushtool.validate(push_conf=modified_store):
        content = json.dumps({LAST_MODIFIED: begin})
        pushtool.push_to(content=content, push_conf=modified_store, group="modified")

    config = params.get("config", {})
    config["sub"] = pushtool.raw_url(push_conf=proxies_store)
    config["saved"] = True
    config["name"] = "v2rayse" if not config.get("name", "") else config.get("name")
    config["push_to"] = list(set(config.get("push_to", [])))

    tasks.append(config)
    return tasks
