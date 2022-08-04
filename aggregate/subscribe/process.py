# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import argparse
import base64
import itertools
import json
import multiprocessing
import os
import random
import re
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass

import yaml

import clash
import crawl
import push
import renewal
import subconverter
import utils
from airport import AirPort

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


@dataclass
class TaskConfig:
    name: str
    domain: str
    sub: str
    index: int
    retry: int
    rate: float
    bin_name: str
    tag: str
    need_verify: bool
    renew: dict


def execute(task_conf: TaskConfig) -> list:
    if not task_conf:
        return []

    obj = AirPort(task_conf.name, task_conf.domain, task_conf.sub)

    # 套餐续期
    if task_conf.renew:
        add_traffic_flow(domain=obj.ref, params=task_conf.renew)

    print(f"start fetch proxy: name=[{task_conf.name}]\tdomain=[{obj.ref}]")
    url, cookie = obj.get_subscribe(
        retry=task_conf.retry, need_verify=task_conf.need_verify
    )
    return obj.parse(
        url,
        cookie,
        task_conf.retry,
        task_conf.rate,
        task_conf.index,
        task_conf.bin_name,
        task_conf.tag,
    )


def cleanup(process: subprocess.Popen, filepath: str, filenames: list = []) -> None:
    for name in filenames:
        filename = os.path.join(filepath, name)
        if os.path.exists(filename):
            os.remove(filename)

    process.terminate()


def add_traffic_flow(domain: str, params: dict) -> None:
    if not domain or not params:
        print(f"[RenewalError] invalidate arguments")
        return
    try:
        email = base64.b64decode(params.get("email", ""))
        password = base64.b64decode(params.get("passwd", ""))
        cookie = renewal.get_cookie(domain=domain, username=email, password=password)
        subscribe_info = renewal.get_subscribe_info(domain=domain, cookie=cookie)
        if not subscribe_info:
            print(f"[RenewalError] cannot fetch subscribe information")
            return

        print(f"subscribe information: domain: {domain}\t{subscribe_info}")
        plan_id = params.get("plan_id", subscribe_info.plan_id)
        package = params.get("package", subscribe_info.package)
        coupon_code = params.get("coupon_code", "")
        method = params.get("method", -1)
        if method <= 0:
            methods = renewal.get_payment_method(domain=domain, cookie=cookie)
            if not methods:
                method = 1
            else:
                method = random.choice(methods)

        payload = {
            "email": email,
            "passwd": password,
            "package": package,
            "plan_id": plan_id,
            "method": method,
            "coupon_code": coupon_code,
        }
        if subscribe_info.reset_enable and subscribe_info.used_rate >= 0.8:
            success = renewal.flow(
                domain=domain, params=payload, reset=True, cookie=cookie
            )
            print(
                "reset {}, domain: {}".format("success" if success else "fail", domain)
            )
        else:
            print(
                f"skip reset traffic plan, domain: {domain}\tenable: {subscribe_info.reset_enable}\tused-rate: {subscribe_info.used_rate}"
            )
        if subscribe_info.renew_enable and subscribe_info.expired_days <= 5:
            success = renewal.flow(
                domain=domain, params=payload, reset=False, cookie=cookie
            )
            print(
                "renew {}, domain: {}".format("success" if success else "fail", domain)
            )
        else:
            print(
                f"skip renew traffic plan, domain: {domain}\tenable: {subscribe_info.renew_enable}\texpired-days: {subscribe_info.expired_days}"
            )
    except:
        traceback.print_exc()


def load_configs(file: str, url: str) -> tuple[list, dict, int]:
    def parse_config(config: dict) -> None:
        sites.extend(config.get("domains", []))
        push_configs.update(config.get("push", {}))
        nonlocal delay
        delay = min(delay, max(config.get("delay", sys.maxsize), 50))

        spiders = config.get("spiders", {})
        telegram_conf = spiders.get("telegram", {})
        disable = telegram_conf.get("disable", False)
        push_to = list(set(telegram_conf.get("push_to", [])))
        items = list(
            set([str(item).strip() for item in telegram_conf.get("users", [])])
        )
        if not disable and items and push_to:
            telegram_conf = crawl_conf.get("telegram", {})
            telegram_conf["period"] = max(telegram_conf.get("period", 7), 7)
            users = telegram_conf.get("users", {})
            for item in items:
                pts = users.get(item, [])
                pts.extend(push_to)
                users[item] = list(set(pts))
            telegram_conf["users"] = users
            crawl_conf["telegram"] = telegram_conf

        google_conf = spiders.get("google", {})
        disable = google_conf.get("disable", False)
        push_to = list(set(google_conf.get("push_to", [])))
        if not disable and push_to:
            pts = crawl_conf.get("google", [])
            pts.extend(push_to)
            crawl_conf["google"] = list(set(pts))

        github_conf = spiders.get("github", {})
        disable = github_conf.get("disable", False)
        push_to = list(set(github_conf.get("push_to", [])))
        pages = github_conf.get("pages", 3)
        exclude = github_conf.get("exclude", "")

        if not disable and push_to:
            github_conf = crawl_conf.get("github", {})
            github_conf["pages"] = max(pages, github_conf.get("pages", 3))
            github_conf["exclude"] = "|".join([exclude, github_conf.get("exclude", "")])
            pts = github_conf.get("push_to", [])
            pts.extend(push_to)
            github_conf["push_to"] = list(set(pts))
            crawl_conf["github"] = github_conf

        repositories = spiders.get("repositories", [])
        repo_conf = crawl_conf.get("repositories", {})
        for repo in repositories:
            disable = repo.get("disable", False)
            username = repo.get("username", "").strip()
            repo_name = repo.get("repo_name", "").strip()
            push_to = list(set(repo.get("push_to", [])))
            commits = max(repo.get("commits", 3), 1)

            if disable or not username or not repo_name:
                continue
            key = "/".join([username, repo_name])
            item = repo_conf.get(key, {})
            item["username"] = username
            item["repo_name"] = repo_name
            item["commits"] = max(commits, item.get("commits", 3))
            pts = item.get("push_to", [])
            pts.extend(push_to)
            item["push_to"] = list(set(push_to))

            repo_conf[key] = item
        crawl_conf["repositories"] = repo_conf

    sites, crawl_conf, push_configs, delay = [], {}, {}, sys.maxsize
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
        if crawl_conf:
            result = crawl.batch_crawl(conf=crawl_conf)
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
            if task.sub != "":
                if task.sub == item.sub:
                    found = True
                    break

            else:
                if task.domain == item.domain and task.index == item.index:
                    found = True
                    break

        if not found:
            items.append(task)

    return items


def assign(
    sites: list,
    retry: int,
    bin_name: str,
    remain: bool,
    params: dict = {},
) -> dict:
    jobs = {}
    retry = max(1, retry)
    for site in sites:
        if not site or site.get("disable", False):
            continue

        name = site.get("name", "").strip().lower()
        domain = site.get("domain", "").strip().lower()
        sub = site.get("sub", "").strip()
        tag = site.get("tag", "").strip().upper()
        rate = float(site.get("rate", 3.0))
        num = min(max(0, int(site.get("count", 1))), 10)
        need_verify = site.get("need_verify", False)
        push_names = site.get("push_to", [])

        if "" == name or ("" == domain and "" == sub) or num <= 0:
            continue

        for idx, push_name in enumerate(push_names):
            if not params.get(push_name, None):
                print(f"cannot found push config, name=[{push_name}]\tsite=[{name}]")
                continue

            tasks = jobs.get(push_name, [])
            renewal = site.get("renewal", {}) if idx == 0 else {}

            if sub != "":
                num = 1

            if num == 1:
                tasks.append(
                    TaskConfig(
                        name=name,
                        domain=domain,
                        sub=sub,
                        index=-1,
                        retry=retry,
                        rate=rate,
                        bin_name=bin_name,
                        tag=tag,
                        need_verify=need_verify,
                        renew=renewal,
                    )
                )
            else:
                subtasks = [
                    TaskConfig(
                        name=name,
                        domain=domain,
                        sub=sub,
                        index=i,
                        retry=retry,
                        rate=rate,
                        bin_name=bin_name,
                        tag=tag,
                        need_verify=need_verify,
                        renew=renewal,
                    )
                    for i in range(1, num + 1)
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
                TaskConfig(
                    name="remains",
                    domain="",
                    sub=sub,
                    index=-1,
                    retry=retry,
                    rate=rate,
                    bin_name=bin_name,
                    tag="R",
                    need_verify=False,
                    renew={},
                )
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
        results = pool.map(execute, v)
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
            print(f"startup clash now, workspace: {workspace}, config: {filename}")
            process = subprocess.Popen(
                [
                    binpath,
                    "-d",
                    workspace,
                    "-f",
                    os.path.join(workspace, filename),
                ]
            )

            print("clash start success")
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
            if len(alive) <= 0:
                print("cannot fetch any proxy, exit")
                sys.exit(0)

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
                push.push_file(filepath, push_configs.get(k, {}), k)

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
