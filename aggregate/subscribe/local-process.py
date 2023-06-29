# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import argparse
import copy
import itertools
import json
import multiprocessing
import os
import random
import subprocess
import sys
import time

import crawl
import executable
import utils
import workflow
import yaml
from airport import FILEPATH_PROTOCAL
from logger import logger
from origin import Origin
from urlvalidator import isurl
from workflow import TaskConfig

import clash

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def load_configs(file: str) -> tuple[list, int]:
    def parse_config(config: dict) -> None:
        sites.extend(config.get("domains", []))
        nonlocal delay
        delay = min(delay, max(config.get("delay", sys.maxsize), 50))

    sites, delay = [], sys.maxsize

    try:
        if os.path.exists(file) and os.path.isfile(file):
            config = json.loads(open(file, "r", encoding="utf8").read())
            parse_config(config)
    except:
        logger.error("occur error when load task config")

    return sites, delay


def assign(
    sites: list,
    retry: int,
    bin_name: str,
    remain: bool,
    filepath: str = "",
    force: bool = False,
) -> list:
    tasks, retry = [], max(1, retry)
    for site in sites:
        if not site:
            continue

        name = site.get("name", "").strip().lower()
        domain = site.get("domain", "").strip().lower()
        subscribes = site.get("sub", "")
        if isinstance(subscribes, str):
            subscribes = [subscribes.strip()]
        subscribes = [s for s in subscribes if s.strip() != ""]
        if len(subscribes) >= 2:
            subscribes = list(set(subscribes))

        tag = site.get("tag", "").strip().upper()
        rate = float(site.get("rate", 3.0))
        num = min(max(1, int(site.get("count", 1))), 10)

        # 如果订阅链接不为空，num为订阅链接数
        num = len(subscribes) if subscribes else num

        source = site.get("origin", "")
        rename = site.get("rename", "")
        exclude = site.get("exclude", "").strip()
        include = site.get("include", "").strip()
        liveness = site.get("liveness", True)
        # 覆盖subconverter默认exclude规则
        ignoreder = site.get("ignorede", False)

        if not source:
            source = Origin.TEMPORARY.name if not domain else Origin.OWNED.name
        site["origin"] = source
        site["name"] = name.rsplit(crawl.SEPARATOR, maxsplit=1)[0]

        renews = copy.deepcopy(site.get("renew", {}))
        accounts = renews.pop("account", [])

        # 如果renew不为空，num为配置的renew账号数
        num = len(accounts) if accounts else num
        disable = site.get("disable", False)
        if disable and force:
            disable = not site.get("force", False)

        if disable or "" == name or ("" == domain and not subscribes) or num <= 0:
            continue

        for i in range(num):
            index = -1 if num == 1 else i + 1
            sub = subscribes[i] if subscribes else ""
            if sub and not isurl(url=sub):
                sub = f"{FILEPATH_PROTOCAL}{sub}"

            renew = {}
            if accounts:
                renew.update(accounts[i])
                renew.update(renews)
                renew["renew"] = True

            tasks.append(
                TaskConfig(
                    name=name,
                    domain=domain,
                    sub=sub,
                    index=index,
                    retry=retry,
                    rate=rate,
                    bin_name=bin_name,
                    tag=tag,
                    renew=renew,
                    rename=rename,
                    exclude=exclude,
                    include=include,
                    liveness=liveness,
                    ignorede=ignoreder,
                )
            )

    if remain:
        if os.path.exists(filepath) and os.path.isfile(filepath):
            tasks.append(
                TaskConfig(
                    name="remains",
                    sub=f"{FILEPATH_PROTOCAL}{filepath}",
                    index=-1,
                    retry=retry,
                    bin_name=bin_name,
                )
            )

    return tasks


def aggregate(args: argparse.Namespace):
    if not args or not args.output:
        logger.error(f"config error, output: {args.output}")
        return

    clash_bin, subconverter_bin = executable.which_bin()

    sites, delay = load_configs(file=args.config)
    tasks = assign(sites, 3, subconverter_bin, args.remain, args.output, args.force)
    if not tasks:
        logger.error("cannot found any valid config, exit")
        sys.exit(0)

    logger.info(f"start generate subscribes information, tasks: {len(tasks)}")
    generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
    if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
        os.remove(generate_conf)

    cpu_count = multiprocessing.cpu_count()
    num = len(tasks) if len(tasks) <= cpu_count else cpu_count

    pool = multiprocessing.Pool(num)
    results = pool.map(workflow.execute, tasks)
    pool.close()

    proxies = list(itertools.chain.from_iterable(results))
    if len(proxies) == 0:
        logger.error("exit because cannot fetch any proxy node")
        sys.exit(0)

    workspace = os.path.join(PATH, "clash")
    binpath = os.path.join(workspace, clash_bin)
    filename = "config.yaml"
    proxies = clash.generate_config(workspace, proxies, filename)

    # 过滤出需要检查可用性的节点
    checks, nochecks = workflow.liveness_fillter(proxies=proxies)

    if checks:
        # 可执行权限
        utils.chmod(binpath)

        with multiprocessing.Manager() as manager:
            availables = manager.list()
            logger.info(
                f"startup clash now, workspace: {workspace}, config: {filename}"
            )
            process = subprocess.Popen(
                [
                    binpath,
                    "-d",
                    workspace,
                    "-f",
                    os.path.join(workspace, filename),
                ]
            )

            logger.info(f"clash start success, begin check proxies, num: {len(checks)}")

            processes = []
            semaphore = multiprocessing.Semaphore(args.num)
            time.sleep(random.randint(3, 6))
            for proxy in checks:
                semaphore.acquire()
                p = multiprocessing.Process(
                    target=clash.check,
                    args=(
                        availables,
                        proxy,
                        clash.EXTERNAL_CONTROLLER,
                        semaphore,
                        args.timeout,
                        args.url,
                        delay,
                        None,
                    ),
                )
                p.start()
                processes.append(p)
            for p in processes:
                p.join()

            nochecks.extend(list(availables))

            # 关闭clash
            try:
                process.terminate()
            except:
                logger.error(f"terminate clash process error")

    if len(nochecks) <= 0:
        logger.error(f"cannot fetch any proxy")
        sys.exit(0)

    data = {"proxies": nochecks}
    filepath = os.path.abspath(os.path.dirname(args.output))
    os.makedirs(filepath, exist_ok=True)
    with open(args.output, "w+", encoding="utf8") as f:
        yaml.dump(data, f, allow_unicode=True)
        logger.info(f"found {len(nochecks)} proxies, save it to {args.output}")

    workflow.cleanup(workspace, [])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-n",
        "--num",
        type=int,
        required=False,
        default=50,
        help="threads num for check proxy",
    )

    parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        required=False,
        default=5000,
        help="timeout",
    )

    parser.add_argument(
        "-u",
        "--url",
        type=str,
        required=False,
        default="https://www.google.com/generate_204",
        help="test url",
    )

    parser.add_argument(
        "-c",
        "--config",
        type=str,
        required=False,
        default=os.path.join(PATH, "subscribe", "config", "local-config.json"),
        help="local config file",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=str,
        required=False,
        default="D:\\Applications\\Clash\\nodepool\\mroxy.yaml",
        help="output file",
    )

    parser.add_argument(
        "-r",
        "--remain",
        dest="remain",
        action="store_true",
        default=True,
        help="include remains proxies",
    )

    parser.add_argument(
        "-f",
        "--force",
        dest="force",
        action="store_true",
        default=False,
        help="forced to join tasks queue",
    )

    args = parser.parse_args()
    aggregate(args=args)
