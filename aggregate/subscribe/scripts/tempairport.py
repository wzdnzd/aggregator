# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-11-12

import json
import multiprocessing

import push
import utils
from airport import AirPort
from crawl import is_available
from logger import logger

from . import commons


def register(domain: str) -> AirPort:
    url = utils.extract_domain(url=domain, include_protocal=True)
    if not url:
        logger.error(
            f"[TempSubError] cannot register because domain=[{domain}] is invalidate"
        )
        return None

    airport = AirPort(name=domain.split("//")[1], site=domain, sub="")
    airport.get_subscribe(retry=3)
    return airport


def fetchsub(params: dict) -> list:
    if not params or type(params) != dict:
        return []

    config = params.get("config", {})
    fileid = params.get("persist", "")
    if not fileid or not config or type(config) != dict or not config.get("push_to"):
        logger.error(
            f"[TempSubError] cannot fetch subscribes bcause not found arguments 'persist' or 'push_to'"
        )
        return []

    exists, unregisters, unknowns = load(fileid=fileid, retry=params.get("retry", True))
    if not exists and not unregisters and unknowns:
        logger.warn(f"[TempSubError] skip fetchsub because cannot get any valid config")
        return []

    if unregisters:
        cpu_count = multiprocessing.cpu_count()
        thread_num = min(len(unregisters), cpu_count * 5)
        pool = multiprocessing.Pool(thread_num)

        airports = pool.map(register, unregisters)
        for airport in airports:
            if not airport:
                continue
            elif not airport.available or not airport.sub:
                logger.warn(
                    f"[TempSubInfo] cannot get subscribe because domain=[{airport.ref}] forced validation or need pay"
                )
                unknowns[airport.ref] = {
                    "sub": airport.sub,
                    "username": airport.username,
                    "password": airport.password,
                }
                continue

            exists[airport.ref] = {
                "sub": airport.sub,
                "username": airport.username,
                "password": airport.password,
            }

        # persist subscribes
        data = {"usables": exists, "unknowns": unknowns}
        commons.persist(data=data, fileid=fileid)

    subscribes = [x.get("sub") for x in exists.values() if x.get("sub", "")]
    subscribes.extend(config.get("sub", []))
    subscribes = list(set(subscribes))

    if not subscribes:
        logger.info(f"[TempSubInfo] fetchsub finished, cannot found any subscribes")
        return []

    config["sub"] = subscribes
    config["name"] = "tempsub" if not config.get("name", "") else config.get("name", "")
    config["push_to"] = list(set(config["push_to"]))

    logger.info(f"[TempSubInfo] fetchsub finished, found {len(subscribes)} subscribes")
    return [config]


def load(fileid: str, retry: bool = False) -> tuple[dict, list, dict]:
    if not fileid:
        return {}, [], {}

    url = push.get_instance().raw_url(fileid.strip())
    try:
        content = utils.http_get(url=url)
        data = json.loads(content)
        if not data:
            return {}, [], {}

        exists, unknowns, unregisters = (
            data.get("usables", {}),
            data.get("unknowns", {}),
            [],
        )
        if retry:
            unregisters, unknowns = list(unknowns.keys()), {}

        if not exists:
            return exists, unregisters, unknowns

        thread_num = min(len(exists), multiprocessing.cpu_count() * 5)
        pool = multiprocessing.Pool(thread_num)
        domains, subscribes = list(exists.keys()), [
            v.get("sub", "") for v in exists.values()
        ]
        results = pool.map(is_available, subscribes)
        for i in range(len(results)):
            if not results[i]:
                exists.pop(domains[i], None)
                unregisters.append(domains[i])

        return exists, list(set(unregisters)), unknowns
    except:
        return {}, [], {}
