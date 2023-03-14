# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-11-12

import json
import multiprocessing
import urllib
import urllib.request
from copy import deepcopy

import push
import utils
from airport import AirPort
from crawl import is_available
from logger import logger
from urlvalidator import isurl

from . import commons, scaner


def register(domain: str, subtype: int = 1, coupon: str = "") -> AirPort:
    url = utils.extract_domain(url=domain, include_protocal=True)
    if not isurl(url=url):
        logger.error(
            f"[TempSubError] cannot register because domain=[{domain}] is invalidate"
        )
        return None

    airport = AirPort(name=domain.split("//")[1], site=url, sub="", coupon=coupon)
    if issspanel(domain=url):
        email = utils.random_chars(length=8, punctuation=False) + "@gmail.com"
        passwd = utils.random_chars(length=10, punctuation=True)
        suburl = scaner.getsub(domain=domain, email=email, passwd=passwd)
        if not utils.isblank(suburl):
            subtype = 1 if subtype < 1 else subtype
            suburl = f"{suburl}?sub={subtype}&extend=1"

        airport.username = email
        airport.password = passwd
        airport.sub = suburl
    else:
        airport.get_subscribe(retry=3)

    return airport


def fetchsub(params: dict) -> list:
    if not params or type(params) != dict:
        return []

    config = params.get("config", {})
    fileid = params.get("persist", "")
    threshold = max(params.get("threshold", 1), 1)
    if not fileid or not config or type(config) != dict or not config.get("push_to"):
        logger.error(
            f"[TempSubError] cannot fetch subscribes bcause not found arguments 'persist' or 'push_to'"
        )
        return []

    exists, unregisters, unknowns, data = load(
        fileid=fileid, retry=params.get("retry", True)
    )
    if not exists and not unregisters and unknowns:
        logger.warn(f"[TempSubError] skip fetchsub because cannot get any valid config")
        return []

    if unregisters:
        cpu_count = multiprocessing.cpu_count()
        thread_num = min(len(unregisters), cpu_count * 5)
        pool = multiprocessing.Pool(thread_num)

        airports = pool.starmap(register, unregisters)
        for airport in airports:
            if not airport:
                continue

            task = data.get("usables", {}).get(airport.ref, {})
            if not task:
                task = data.get("unknowns", {}).get(airport.ref, {})

            if not airport.available or not airport.sub:
                logger.error(
                    f"[TempSubInfo] cannot get subscribe because domain=[{airport.ref}] forced validation or need pay"
                )
                if not utils.isblank(airport.sub):
                    logger.warn(
                        f"[TempSubInfo] renew error, domain: {airport.ref} username: {airport.username} password: {airport.password} sub: {airport.sub}"
                    )

                defeat = task.get("defeat", 0) + 1
                if defeat > threshold:
                    task["enable"] = False
                task["defeat"] = defeat
                unknowns[airport.ref] = task
            else:
                task.update(
                    {
                        "sub": airport.sub,
                        "username": airport.username,
                        "password": airport.password,
                        "defeat": 0,
                    }
                )
                exists[airport.ref] = task

        # persist subscribes
        payload = {"usables": exists, "unknowns": unknowns}
        commons.persist(data=payload, fileid=fileid)

    if not exists:
        logger.info(f"[TempSubInfo] fetchsub finished, cannot found any subscribes")
        return []

    results = []
    for subscribe in exists.values():
        if not subscribe.get("enable", True):
            continue

        item = deepcopy(config)
        item["sub"] = subscribe.get("sub")
        if "config" in subscribe:
            item.update(subscribe.get("config"))

        if utils.isblank(item.get("name", "")):
            item["name"] = utils.extract_domain(
                url=item["sub"], include_protocal=False
            ).replace(".", "-")
        item["push_to"] = list(set(item.get("push_to", [])))
        results.append(item)

    logger.info(f"[TempSubInfo] fetchsub finished, found {len(results)} subscribes")
    return results


def load(fileid: str, retry: bool = False) -> tuple[dict, list, dict, dict]:
    if not fileid:
        return {}, [], {}, {}

    url = push.get_instance().raw_url(fileid.strip())
    try:
        content = utils.http_get(url=url)
        data = json.loads(content)
        if not data:
            return {}, [], {}, {}

        exists, unknowns, unregisters = (
            data.get("usables", {}),
            data.get("unknowns", {}),
            [],
        )
        # 保存旧有配置
        rawdata = deepcopy(data)

        if retry and unknowns:
            for k in list(unknowns.keys()):
                v = unknowns.get(k, {})
                if v and v.get("enable", True):
                    # 包含订阅，再次检测，否则重新注册
                    if not utils.isblank(v.get("sub", "")):
                        exists[k] = v
                    else:
                        unregisters.append([k, v.get("type", 1), v.get("coupon", "")])
                    unknowns.pop(k, None)

        domains, subscribes = [], []
        for k, v in exists.items():
            if not v or not v.get("enable", True):
                continue
            domains.append(k)
            subscribes.append(v.get("sub", ""))

        if not domains:
            return exists, unregisters, unknowns, rawdata

        thread_num = min(len(domains), multiprocessing.cpu_count() * 5)
        pool = multiprocessing.Pool(thread_num)
        results = pool.map(is_available, subscribes)

        for i in range(len(results)):
            if not results[i]:
                item = exists.pop(domains[i], {})
                unregisters.append(
                    [domains[i], item.get("type", 1), item.get("coupon", "")]
                )

        # 去重
        if unregisters:
            data = {x[0]: [x[1], x[2]] for x in unregisters}
            unregisters = [[k, v[0], v[1]] for k, v in data.items()]

        return exists, unregisters, unknowns, rawdata
    except:
        return {}, [], {}, {}


class NoRedirHandler(urllib.request.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        return fp

    http_error_301 = http_error_302


def sniff(url: str) -> int:
    if utils.isblank(url):
        return -1

    try:
        opener = urllib.request.build_opener(NoRedirHandler)
        opener.addheaders = [("User-Agent", utils.USER_AGENT)]
        response = opener.open(fullurl=url, timeout=10)
        return response.getcode()
    except Exception:
        return -2


def issspanel(domain: str) -> bool:
    url = f"{domain}/api/v1/passport/auth/login"
    return False if sniff(url=url) == 200 else sniff(url=f"{domain}/auth/login") == 200
