# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import argparse
import itertools
import json
import multiprocessing
import os
import random
import re
import subprocess
import sys
import time

import yaml

import clash
import crawl
import push
import subconverter
import utils
from airport import AirPort

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def execute(
    name,
    url: str,
    sub: str,
    index: int,
    retry: int,
    rate: float,
    bin_name: str,
    tag: str,
    need_verify: bool,
) -> list:
    obj = AirPort(name, url, sub)

    print(f"start fetch proxy: name=[{name}]\tdomain=[{url}]")
    url, cookie = obj.get_subscribe(retry=retry, need_verify=need_verify)
    return obj.parse(url, cookie, retry, rate, index, bin_name, tag.upper())


def cleanup(process: subprocess.Popen, filepath: str, filenames: list = []) -> None:
    for name in filenames:
        filename = os.path.join(filepath, name)
        if os.path.exists(filename):
            os.remove(filename)

    process.terminate()


def load_configs(file: str, url: str) -> tuple[list, dict, int]:
    def parse_config(config: dict) -> None:
        sites.extend(config.get("domains", []))
        push_configs.update(config.get("push", {}))
        nonlocal delay
        delay = min(delay, max(config.get("delay", sys.maxsize), 50))

        telegram = config.get("telegram", {})
        disable = telegram.get("disable", False)
        push_to = list(set(telegram.get("push_to", [])))
        items = list(set([str(item).strip() for item in telegram.get("users", [])]))
        if not disable and items and push_to:
            for item in items:
                ps = users.get(item, [])
                ps.extend(push_to)
                users[item] = list(set(ps))

    sites, users, push_configs, delay = [], {}, {}, sys.maxsize
    try:
        if os.path.exists(file) and os.path.isfile(file):
            config = json.loads(open(file, "r", encoding="utf8").read())
            parse_config(config)

        if re.match(
            "^(https?:\/\/(([a-zA-Z0-9]+-?)+[a-zA-Z0-9]+\.)+[a-zA-Z]+)(:\d+)?(\/.*)?(\?.*)?(#.*)?$",
            url,
        ):
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.114 Safari/537.36 Edg/103.0.1264.62",
                "Referer": url,
            }

            content = utils.http_get(url=url, headers=headers)
            if not content:
                print(f"cannot fetch config from remote, url: {url}")
            else:
                parse_config(json.loads(content))

        # 从telegram抓取订阅信息
        if users:
            result = crawl.batch_crawl(users, 7)
            sites.extend(result)
    except:
        print("occur error when load task config")

    return sites, push_configs, delay


def dedup_task(tasks: list) -> list:
    if not tasks:
        return []
    items = []
    for task in tasks:
        found = False
        for item in items:
            if task[2] != "":
                if task[2] == item[2]:
                    found = True
                    break

            else:
                if task[1] == item[1] and task[3] == item[3]:
                    found = True
                    break

        if not found:
            items.append(task)

    return items


def assign(
    sites: list,
    retry: int,
    subconverter: str,
    remain: bool,
    params: dict = {},
) -> dict:
    jobs = {}
    retry = max(1, retry)
    for site in sites:
        if not site or site.get("disable", False):
            continue

        name = site.get("name", "").strip().lower()
        url = site.get("url", "").strip().lower()
        sub = site.get("sub", "").strip()
        tag = site.get("tag", "").strip()
        rate = float(site.get("rate", 3.0))
        num = min(max(0, int(site.get("count", 1))), 10)
        need_verify = site.get("need_verify", False)
        push_names = site.get("push_to", [])

        if "" == name or ("" == url and "" == sub) or num <= 0:
            continue

        for push_name in push_names:
            if not params.get(push_name, None):
                print(f"cannot found push config, name=[{push_name}]\tsite=[{name}]")
                continue

            tasks = jobs.get(push_name, [])

            if sub != "":
                num = 1

            if num == 1:
                tasks.append(
                    [name, url, sub, -1, retry, rate, subconverter, tag, need_verify]
                )
            else:
                subtasks = [
                    [name, url, sub, i, retry, rate, subconverter, tag, need_verify]
                    for i in range(num)
                ]
                tasks.extend(subtasks)

            jobs[push_name] = tasks

    if remain and params:
        for k, v in params.items():
            tasks = jobs.get(k, [])
            folderid = v.get("folderid", "").strip()
            fileid = v.get("fileid", "").strip()
            username = v.get("username", "").strip()
            if not folderid or not fileid or not username:
                continue

            sub = f"https://paste.gg/p/{username}/{folderid}/files/{fileid}/raw"
            tasks.append(
                ["remains", "", sub, -1, retry, rate, subconverter, "R", False]
            )
            jobs[k] = tasks
    return jobs


def aggregate(args: argparse.Namespace):
    if not args:
        return

    clash_bin, subconverter_bin = clash.which_bin()

    sites, push_configs, delay = load_configs(file=args.file, url=args.server)
    push_configs = push.validate_push(push_configs)
    tasks = assign(sites, 3, subconverter_bin, args.remain, push_configs)
    if not tasks:
        print("cannot found any valid config, exit")
        sys.exit(0)

    for k, v in tasks.items():
        v = dedup_task(v)
        if not v:
            print(f"task is empty, group=[{k}]")
            continue

        print(f"start generate subscribes information, group=[{k}]")
        generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
        if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
            os.remove(generate_conf)

        cpu_count = multiprocessing.cpu_count()
        num = len(v) if len(v) <= cpu_count else cpu_count

        pool = multiprocessing.Pool(num)
        results = pool.starmap(execute, v)
        pool.close()

        proxies = list(itertools.chain.from_iterable(results))
        if len(proxies) == 0:
            print(f"exit because cannot fetch any proxy node, group=[{k}]")
            continue

        workspace = os.path.join(PATH, "clash")
        binpath = os.path.join(workspace, clash_bin)
        filename = "config.yaml"
        proxies = clash.generate_config(workspace, proxies, filename)

        utils.chmod(binpath)
        with multiprocessing.Manager() as manager:
            alive = manager.list()
            process = subprocess.Popen(
                [
                    binpath,
                    "-d",
                    workspace,
                    "-f",
                    os.path.join(workspace, filename),
                ]
            )

            processes = []
            semaphore = multiprocessing.Semaphore(args.num)
            time.sleep(random.randint(3, 6))
            for proxy in proxies:
                semaphore.acquire()
                p = multiprocessing.Process(
                    target=clash.check,
                    args=(
                        alive,
                        proxy,
                        clash.EXTERNAL_CONTROLLER,
                        semaphore,
                        args.timeout,
                        args.url,
                        delay,
                    ),
                )
                p.start()
                processes.append(p)
            for p in processes:
                p.join()

            time.sleep(random.randint(3, 6))
            data = {"proxies": list(alive)}
            source_file = "config.yaml"
            filepath = os.path.join(PATH, "subconverter", source_file)
            with open(filepath, "w+", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True)

            # 转换成通用订阅模式
            dest_file = "subscribe.txt"
            artifact = "convert"

            if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
                os.remove(generate_conf)

            success = subconverter.generate_conf(
                generate_conf, artifact, source_file, dest_file, "mixed"
            )
            if not success:
                print(f"cannot generate subconverter config file, group=[{k}]")
                continue

            if subconverter.convert(binname=subconverter_bin, artifact=artifact):
                # 推送到https://paste.gg
                filepath = os.path.join(PATH, "subconverter", dest_file)
                push.push_to(filepath, push_configs.get(k, {}), k)

            # 关闭clash
            cleanup(
                process,
                os.path.join(PATH, "subconverter"),
                [source_file, dest_file, "generate.ini"],
            )


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
        "-f",
        "--file",
        type=str,
        required=False,
        default=os.path.join(PATH, "subscribe", "config", "config.json"),
        help="local config file",
    )

    parser.add_argument(
        "-s",
        "--server",
        type=str,
        required=False,
        default="",
        help="remote config file",
    )

    parser.add_argument(
        "-r",
        "--remain",
        dest="remain",
        action="store_true",
        default=True,
        help="include remains proxies",
    )

    args = parser.parse_args()
    aggregate(args=args)
