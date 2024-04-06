# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import argparse

# import itertools
import multiprocessing
import os
import random
import subprocess
import sys
import time
import traceback
from multiprocessing.managers import ListProxy
from multiprocessing.synchronize import Semaphore

import clash
import crawl
import executable
import utils
import workflow
import yaml
from logger import logger
from workflow import TaskConfig

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def assign(
    retry: int,
    bin_name: str,
    filename: str = "",
    overwrite: bool = False,
    pages: int = sys.maxsize,
    rigid: bool = True,
) -> list:
    domains = []
    if filename and os.path.exists(filename) and os.path.isfile(filename):
        with open(filename, "r", encoding="UTF8") as f:
            for line in f.readlines():
                line = line.replace("\n", "").strip()
                if not line:
                    continue
                domains.append(line)

    if not domains or overwrite:
        urls = crawl.collect_airport(channel="jichang_list", page_num=pages, rigid=rigid)
        domains.extend(urls)
        overwrite = True

    domains = list(set(domains))
    tasks, retry = [], max(1, retry)
    if not domains:
        logger.error("[CrawlError] cannot collect any airport for free use")
        return tasks

    if overwrite:
        utils.write_file(filename=filename, lines=domains)

    for domain in domains:
        name = crawl.naming_task(url=domain)
        tasks.append(TaskConfig(name=name, domain=domain, bin_name=bin_name))

    return tasks


def execute(config: TaskConfig, proxies: ListProxy, semaphore: Semaphore) -> None:
    try:
        result = workflow.execute(task_conf=config)
        if result and proxies != None:
            proxies.extend(result)
    except:
        traceback.print_exc()
    finally:
        if semaphore is not None and isinstance(semaphore, Semaphore):
            semaphore.release()


def aggregate(args: argparse.Namespace):
    if not args or not args.output:
        logger.error(f"config error, output: {args.output}")
        return

    clash_bin, subconverter_bin = executable.which_bin()
    tasks = assign(
        retry=3,
        bin_name=subconverter_bin,
        filename=os.path.join(PATH, "domains.txt"),
        overwrite=args.overwrite,
        pages=args.pages,
        rigid=not args.relaxed,
    )

    if not tasks:
        logger.error("cannot found any valid config, exit")
        sys.exit(0)

    logger.info(f"start generate subscribes information, tasks: {len(tasks)}")
    generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
    if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
        os.remove(generate_conf)

    with multiprocessing.Manager() as manager:
        proxies, processes = manager.list(), []
        semaphore = multiprocessing.Semaphore(args.num)

        for task in tasks:
            semaphore.acquire()
            p = multiprocessing.Process(target=execute, args=(task, proxies, semaphore))
            p.start()
            processes.append(p)
        for p in processes:
            p.join()

        # 清除任务
        processes.clear()

        # cpu_count = multiprocessing.cpu_count()
        # num = len(tasks) if len(tasks) <= cpu_count else cpu_count

        # pool = multiprocessing.Pool(num)
        # results = pool.map(workflow.execute, tasks)
        # pool.close()

        # proxies = list(itertools.chain.from_iterable(results))

        if len(proxies) == 0:
            logger.error("exit because cannot fetch any proxy node")
            sys.exit(0)

        workspace = os.path.join(PATH, "clash")

        if args.skip:
            nodes, subscriptions = [], set()
            for p in proxies:
                if not p or not isinstance(p, dict):
                    continue

                # remove unused key
                p.pop("chatgpt", False)
                sub = p.pop("sub", "")
                if sub:
                    subscriptions.add(sub)

                nodes.append(p)

            data = {"proxies": nodes}
            urls = list(subscriptions)
        else:
            binpath = os.path.join(workspace, clash_bin)
            filename = "config.yaml"
            proxies = clash.generate_config(workspace, list(proxies), filename)

            # 可执行权限
            utils.chmod(binpath)

            nodes, availables = manager.list(), manager.dict()
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
            for proxy in proxies:
                semaphore.acquire()
                p = multiprocessing.Process(
                    target=clash.check,
                    args=(
                        nodes,
                        proxy,
                        clash.EXTERNAL_CONTROLLER,
                        semaphore,
                        args.timeout,
                        args.url,
                        args.delay,
                        availables,
                    ),
                )
                p.start()
                processes.append(p)
            for p in processes:
                p.join()

            time.sleep(random.randint(1, 3))

            # 关闭clash
            try:
                process.terminate()
            except:
                logger.error(f"terminate clash process error")

            if len(nodes) <= 0:
                logger.error(f"cannot fetch any proxy")
                sys.exit(0)

            data = {"proxies": list(nodes)}
            urls = availables.keys()

        os.makedirs(args.output, exist_ok=True)
        proxies_file = os.path.join(args.output, args.filename)
        with open(proxies_file, "w+", encoding="utf8") as f:
            yaml.dump(data, f, allow_unicode=True)
            logger.info(f"found {len(nodes)} proxies, save it to {proxies_file}")

        utils.write_file(filename=os.path.join(args.output, "subscribes.txt"), lines=urls)
        domains = [utils.extract_domain(url=x, include_protocal=True) for x in urls]

        # 更新 domains.txt 文件为实际可使用的网站列表
        utils.write_file(filename=os.path.join(PATH, "valid-domains.txt"), lines=domains)
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
        "-d",
        "--delay",
        type=int,
        required=False,
        default=5000,
        help="proxies max delay allowed",
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
        "-o",
        "--output",
        type=str,
        required=False,
        default=PATH,
        help="output directory",
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
        "-w",
        "--overwrite",
        dest="overwrite",
        action="store_true",
        default=False,
        help="overwrite domains",
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

    args = parser.parse_args()
    aggregate(args=args)
