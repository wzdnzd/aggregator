# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-11-12

import json
from copy import deepcopy

import push
import utils
from airport import AirPort, issspanel
from crawl import is_available
from logger import logger
from urlvalidator import isurl

from . import commons, scaner


def register(
    domain: str, subtype: int = 1, coupon: str = "", rigid: bool = True, chuck: bool = False, invite_code: str = ""
) -> AirPort:
    url = utils.extract_domain(url=domain, include_protocal=True)
    if not isurl(url=url):
        logger.error(f"[TempSubError] cannot register because domain=[{domain}] is invalidate")
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
        airport.get_subscribe(retry=3, rigid=rigid, chuck=chuck, invite_code=invite_code)

    return airport


def fetchsub(params: dict) -> list:
    if not params or type(params) != dict:
        return []

    config = params.get("config", {})
    persist = params.get("persist", {})
    engine = params.get("engine", "")

    threshold = max(params.get("threshold", 1), 1)
    if not persist or not config or type(config) != dict or not config.get("push_to"):
        logger.error(f"[TempSubError] cannot fetch subscribes bcause not found arguments 'persist' or 'push_to'")
        return []

    exists, unregisters, unknowns, data = load(engine=engine, persist=persist, retry=params.get("retry", True))
    if not exists and not unregisters and unknowns:
        logger.warning(f"[TempSubError] skip fetchsub because cannot get any valid config")
        return []

    if unregisters:
        airports = utils.multi_thread_run(func=register, tasks=unregisters)
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
                    logger.warning(
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
        commons.persist(engine=engine, data=payload, persist=persist)

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
            item["name"] = utils.extract_domain(url=item["sub"], include_protocal=False).replace(".", "-")
        item["push_to"] = list(set(item.get("push_to", [])))
        item["saved"] = True
        results.append(item)

    logger.info(f"[TempSubInfo] fetchsub finished, found {len(results)} subscribes")
    return results


def load(engine: str, persist: dict, retry: bool = False) -> tuple[dict, list, dict, dict]:
    pushtool = push.get_instance(engine=engine)
    if not pushtool.validate(push_conf=persist):
        return {}, [], {}, {}

    url = pushtool.raw_url(push_conf=persist)
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
                        coupon = v.get("coupon", "")
                        rigid = v.get("rigid", True)
                        chuck = v.get("chuck", False)
                        invite_code = v.get("invite_code", "")

                        unregisters.append([k, v.get("type", 1), coupon, rigid, chuck, invite_code])

                    unknowns.pop(k, None)

        domains, subscribes = [], []
        for k, v in exists.items():
            if not v or not v.get("enable", True):
                continue
            domains.append(k)
            subscribes.append([v.get("sub", ""), 2, 0.5, 1.0])

        if not domains:
            return exists, unregisters, unknowns, rawdata

        results = utils.multi_thread_run(func=is_available, tasks=subscribes)
        for i in range(len(results)):
            if not results[i]:
                item = exists.pop(domains[i], {})
                unregisters.append([domains[i], item.get("type", 1), item.get("coupon", "")])

        # 去重
        if unregisters:
            data = {x[0]: [x[1], x[2]] for x in unregisters}
            unregisters = [[k, v[0], v[1]] for k, v in data.items()]

        return exists, unregisters, unknowns, rawdata
    except:
        return {}, [], {}, {}
