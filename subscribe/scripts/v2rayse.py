# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2023-06-30

import base64
import itertools
import json
import os
import re
import sys
import time
import traceback
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

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
from clash import QuotedStr, quoted_scalar

# outbind type
SUPPORT_TYPE = ["ss", "ssr", "vmess", "trojan", "snell", "vless", "hysteria2", "hysteria", "http", "socks5"]

# date format
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# last modified key name
LAST_MODIFIED = "lastModified"

# whether enable special protocols
SPECIAL_PROTOCOLS = AirPort.enable_special_protocols()


def current_time(utc: bool = True) -> datetime:
    now = datetime.now(timezone.utc)
    if not utc:
        tz = timezone(timedelta(hours=8), name="Asia/Shanghai")
        now = now.replace(tzinfo=tz.utc).astimezone(tz)

    return now


def get_dates(last: datetime) -> list[str]:
    last, dates = last if last else current_time(utc=True), []

    start = last.replace(hour=0, minute=0, second=0).replace(tzinfo=timezone.utc)
    end = current_time(utc=True).replace(hour=23, minute=59, second=59)

    while start <= end:
        dates.append(start.strftime("%Y%m%d"))
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

    return last.replace(tzinfo=timezone.utc)


def list_files(base: str, date: str, maxsize: int, last: datetime) -> list[str]:
    marker, truncated, count = "", True, 0
    base, date = utils.trim(base), utils.trim(date)
    prefix, files = f"{base}?prefix={date}/", []

    while truncated and count < 3:
        count += 1
        url = prefix if not marker else f"{prefix}&marker={marker}"
        try:
            content = utils.http_get(url=url)
            if content and content.startswith("<?xml"):
                content = content.split("?>", maxsplit=1)[1].removeprefix("\n")

            document = ElementTree.fromstring(content)
            namespace = {"ns": "http://s3.amazonaws.com/doc/2006-03-01/"}

            #  IsTruncated being true means the number of keys exceeds 1000, and pagination is required
            is_truncated = document.find(path="ns:IsTruncated", namespaces=namespace)
            truncated = utils.trim(is_truncated.text).lower() in ("true", "1") if is_truncated else False

            # NextMarker indicates the start key for the next page
            next_marker = document.find(path="ns:NextMarker", namespaces=namespace)
            marker = next_marker.text if next_marker else ""

            for item in document.iterfind(path="ns:Contents", namespaces=namespace):
                name = item.findtext(path="ns:Key", default="", namespaces=namespace)
                if not name:
                    continue

                try:
                    # filter by file size
                    size = int(item.findtext(path="ns:Size", default="0", namespaces=namespace))
                    if size > maxsize:
                        continue

                    # filter by last modified time
                    updated_at = item.findtext(path="ns:LastModified", default="", namespaces=namespace)
                    if updated_at:
                        modified = datetime.fromisoformat(updated_at[:-1]).replace(tzinfo=timezone.utc)
                        if modified < last:
                            continue
                except:
                    logger.error(f"[V2RaySE] parse details of the file {name} error")

                files.append(f"{base}/{name}")
        except:
            logger.error(f"[V2RaySE] list files error, date: {date}, marker: {marker}")

    return files


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
        regex = r"(?:https?://)?(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+(?:(?:(?:/index.php)?/api/v1/client/subscribe\?token=[a-zA-Z0-9]{16,32})|(?:/link/[a-zA-Z0-9]+\?(?:sub|mu|clash)=\d))|https://jmssub\.net/members/getsub\.php\?service=\d+&id=[a-zA-Z0-9\-]{36}(?:\S+)?"
        groups = re.findall(regex, content, flags=re.I)
        if groups:
            subscriptions = list(set([utils.url_complete(x) for x in groups if x]))

    if not noproxies:
        try:
            index = url.rfind("/")
            if index != -1:
                name = url[index + 1 :]
            else:
                name = utils.random_chars(length=6, punctuation=False)

            proxies = AirPort.decode(
                text=content,
                program=subconverter,
                artifact=name,
                special=SPECIAL_PROTOCOLS,
                throw=True,
            )

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
    pushtool = push.get_instance(engine=params.get("engine", ""))
    if not persist or type(persist) != dict or not pushtool.validate(persist.get("proxies", {})):
        logger.error(f"[V2RaySE] invalid persist config, please check it and try again")
        return []

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
        last = datetime(time.strptime("1970-01-01 00:00:00", DATE_FORMAT)[:6]).replace(tzinfo=timezone.utc)
        logger.info(f"[V2RaySE] begin crawl data, dates: {dates}")
    else:
        logger.info(f"[V2RaySE] begin crawl data from [{last.strftime(DATE_FORMAT)}] to [{begin}]")

    base, starttime = f"{domain}/share", time.time()
    partitions = [[base, date, maxsize, last] for date in dates]

    links = utils.multi_thread_run(func=list_files, tasks=partitions)
    files = list(set(itertools.chain.from_iterable(links)))
    array = [[x, nopublic, exclude, ignore, repeat, noproxies] for x in files if x]

    if not array:
        logger.error(f"[V2RaySE] cannot found any valid shared file, dates: {dates}")
        return []

    logger.info(f"[V2RaySE] start to fetch shared files, count: {len(array)}")

    tasks, proxies, subscriptions = [], [], set()
    results = utils.multi_process_run(func=fetchone, tasks=array)

    for result in results:
        proxies.extend([p for p in result[0] if p and p.get("name", "") and p.get("type", "") in support])
        subscriptions.update([x for x in result[1] if x])

    cost = "{:.2f}s".format(time.time() - starttime)
    logger.info(
        f"[V2RaySE] finished crawl tasks, cost: {cost}, found {len(proxies)} proxies and {len(subscriptions)} subscriptions: {list(subscriptions)}"
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
        yaml.add_representer(QuotedStr, quoted_scalar)
        yaml.dump(data, f, allow_unicode=True)

    if os.path.exists(generate) and os.path.isfile(generate):
        os.remove(generate)

    success = subconverter.generate_conf(generate, artifact, source, dest, "mixed")
    if not success:
        logger.error(f"[V2RaySE] cannot generate subconverter config file")
        yaml.add_representer(QuotedStr, quoted_scalar)
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

    success = pushtool.push_to(content=content or " ", push_conf=proxies_store, group="v2rayse")
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
