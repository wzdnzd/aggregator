# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import argparse
import itertools
import os
import random
import subprocess
import sys
import time

import clash
import crawl
import executable
import utils
import workflow
import yaml
from logger import logger
from workflow import TaskConfig

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

DATA_BASE = os.path.join(PATH, "data")


def assign(
    bin_name: str,
    filename: str = "",
    overwrite: bool = False,
    pages: int = sys.maxsize,
    rigid: bool = True,
    display: bool = True,
    num_threads: int = 0,
) -> list[TaskConfig]:
    domains, delimiter = {}, "@#@#"
    if filename and os.path.exists(filename) and os.path.isfile(filename):
        with open(filename, "r", encoding="UTF8") as f:
            for line in f.readlines():
                line = line.replace("\n", "").strip()
                if not line:
                    continue

                words = line.rsplit(delimiter, maxsplit=1)
                address = utils.trim(words[0])
                coupon = utils.trim(words[1]) if len(words) > 1 else ""

                domains[address] = coupon

    if not domains or overwrite:
        candidates = crawl.collect_airport(
            channel="jichang_list",
            page_num=pages,
            num_thread=num_threads,
            rigid=rigid,
            display=display,
        )

        if candidates:
            domains.update(candidates)
            overwrite = True

    if not domains:
        logger.error("[CrawlError] cannot collect any airport for free use")
        return []

    if overwrite:
        lines = []
        for k, v in domains.items():
            if not v:
                lines.append(k)
            else:
                lines.append(f"{k}\t{delimiter}\t{v}")

        utils.write_file(filename=filename, lines=lines)

    tasks = list()
    for domain, coupon in domains.items():
        name = crawl.naming_task(url=domain)
        tasks.append(TaskConfig(name=name, domain=domain, coupon=coupon, bin_name=bin_name, rigid=rigid))

    return tasks


def aggregate(args: argparse.Namespace) -> None:
    if not args or not args.output:
        logger.error(f"config error, output: {args.output}")
        return

    clash_bin, subconverter_bin = executable.which_bin()
    display = not args.invisible

    tasks = assign(
        bin_name=subconverter_bin,
        filename=os.path.join(DATA_BASE, "domains.txt"),
        overwrite=args.overwrite,
        pages=args.pages,
        rigid=not args.relaxed,
        display=display,
        num_threads=args.num,
    )

    if not tasks:
        logger.error("cannot found any valid config, exit")
        sys.exit(0)

    logger.info(f"start generate subscribes information, tasks: {len(tasks)}")
    generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
    if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
        os.remove(generate_conf)

    results = utils.multi_thread_run(func=workflow.executewrapper, tasks=tasks, num_threads=args.num)
    proxies = list(itertools.chain.from_iterable([x[1] for x in results if x]))

    if len(proxies) == 0:
        logger.error("exit because cannot fetch any proxy node")
        sys.exit(0)

    nodes, workspace = [], os.path.join(PATH, "clash")

    if args.skip:
        nodes = [p for p in proxies if p and isinstance(p, dict)]
    else:
        binpath = os.path.join(workspace, clash_bin)
        filename = "config.yaml"
        proxies = clash.generate_config(workspace, list(proxies), filename)

        # 可执行权限
        utils.chmod(binpath)

        logger.info(f"startup clash now, workspace: {workspace}, config: {filename}")
        process = subprocess.Popen(
            [
                binpath,
                "-d",
                workspace,
                "-f",
                os.path.join(workspace, filename),
            ]
        )
        logger.info(f"clash start success, begin check proxies, num: {len(proxies)}")

        time.sleep(random.randint(3, 6))
        params = [
            [p, clash.EXTERNAL_CONTROLLER, args.timeout, args.url, args.delay, False]
            for p in proxies
            if isinstance(p, dict)
        ]

        masks = utils.multi_thread_run(
            func=clash.check,
            tasks=params,
            num_threads=args.num,
            show_progress=display,
        )

        # 关闭clash
        try:
            process.terminate()
        except:
            logger.error(f"terminate clash process error")

        nodes = [proxies[i] for i in range(len(proxies)) if masks[i]]
        if len(nodes) <= 0:
            logger.error(f"cannot fetch any proxy")
            sys.exit(0)

    subscriptions = set()
    for p in proxies:
        # remove unused key
        p.pop("chatgpt", False)
        p.pop("liveness", True)

        sub = p.pop("sub", "")
        if sub:
            subscriptions.add(sub)

    data = {"proxies": nodes}
    urls = list(subscriptions)

    os.makedirs(args.output, exist_ok=True)
    proxies_file = os.path.join(args.output, args.filename)
    with open(proxies_file, "w+", encoding="utf8") as f:
        yaml.dump(data, f, allow_unicode=True)
        logger.info(f"found {len(nodes)} proxies, save it to {proxies_file}")

    life, vestigial = max(0, args.life), max(0, args.vestigial)
    if life > 0 or vestigial > 0:
        tasks = [[x, 2, vestigial, life, 0, True] for x in urls]
        results = utils.multi_thread_run(
            func=crawl.check_status,
            tasks=tasks,
            num_threads=args.num,
            show_progress=display,
        )

        urls = [urls[i] for i in range(len(urls)) if results[i][0] and not results[i][1]]
        discard = len(tasks) - len(urls)

        logger.info(f"filter subscriptions finished, total: {len(tasks)}, found: {len(urls)}, discard: {discard}")

    utils.write_file(filename=os.path.join(args.output, "subscribes.txt"), lines=urls)
    domains = [utils.extract_domain(url=x, include_protocal=True) for x in urls]

    # 更新 domains.txt 文件为实际可使用的网站列表
    utils.write_file(filename=os.path.join(args.output, "valid-domains.txt"), lines=list(set(domains)))
    workflow.cleanup(workspace, [])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d",
        "--delay",
        type=int,
        required=False,
        default=5000,
        help="proxies max delay allowed",
    )

    parser.add_argument(
        "-f",
        "--filename",
        type=str,
        required=False,
        default="proxies.yaml",
        help="proxies filename",
    )

    parser.add_argument(
        "-i",
        "--invisible",
        dest="invisible",
        action="store_true",
        default=False,
        help="don't show check progress bar",
    )

    parser.add_argument(
        "-l",
        "--life",
        type=int,
        required=False,
        default=0,
        help="remaining life time, unit: hours",
    )

    parser.add_argument(
        "-n",
        "--num",
        type=int,
        required=False,
        default=64,
        help="threads num for check proxy",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=str,
        required=False,
        default=DATA_BASE,
        help="output directory",
    )

    parser.add_argument(
        "-p",
        "--pages",
        type=int,
        required=False,
        default=sys.maxsize,
        help="crawl page num",
    )

    parser.add_argument(
        "-r",
        "--relaxed",
        dest="relaxed",
        action="store_true",
        default=False,
        help="try registering with a gmail alias when you encounter a whitelisted mailbox",
    )

    parser.add_argument(
        "-s",
        "--skip",
        dest="skip",
        action="store_true",
        default=False,
        help="skip usability checks",
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
        "-v",
        "--vestigial",
        type=int,
        required=False,
        default=0,
        help="vestigial traffic allowed to use, unit: GB",
    )

    parser.add_argument(
        "-w",
        "--overwrite",
        dest="overwrite",
        action="store_true",
        default=False,
        help="overwrite domains",
    )

    aggregate(args=parser.parse_args())
