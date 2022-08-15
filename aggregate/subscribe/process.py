# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import argparse
import base64
import copy
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
from origin import Origin

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
    rename: str = ""
    exclude: str = ""
    include: str = ""


def execute(task_conf: TaskConfig) -> list:
    if not task_conf:
        return []

    obj = AirPort(
        name=task_conf.name,
        site=task_conf.domain,
        sub=task_conf.sub,
        rename=task_conf.rename,
        exclude=task_conf.exclude,
        include=task_conf.include,
    )

    # 套餐续期
    if task_conf.renew:
        token = add_traffic_flow(domain=obj.ref, params=task_conf.renew)
        if token and not obj.registed:
            obj.registed = True
            obj.sub = obj.sub + token

    print(f"start fetch proxy: name=[{task_conf.name}]\tdomain=[{obj.ref}]")
    url, cookie = obj.get_subscribe(
        retry=task_conf.retry, need_verify=task_conf.need_verify
    )
    return obj.parse(
        url,
        cookie,
        task_conf.retry,
        task_conf.rate,
        task_conf.bin_name,
        task_conf.tag,
    )


def cleanup(process: subprocess.Popen, filepath: str, filenames: list = []) -> None:
    for name in filenames:
        filename = os.path.join(filepath, name)
        if os.path.exists(filename):
            os.remove(filename)

    process.terminate()


def add_traffic_flow(domain: str, params: dict) -> str:
    if not domain or not params:
        print(f"[RenewalError] invalidate arguments")
        return ""
    try:
        email = base64.b64decode(params.get("email", ""))
        password = base64.b64decode(params.get("passwd", ""))
        cookies, authorization = renewal.get_cookies(
            domain=domain, username=email, password=password
        )
        subscribe_info = renewal.get_subscribe_info(
            domain=domain, cookies=cookies, authorization=authorization
        )
        if not subscribe_info:
            print(f"[RenewalError] cannot fetch subscribe information")
            return ""

        print(f"subscribe information: domain: {domain}\t{subscribe_info}")
        plan_id = params.get("plan_id", subscribe_info.plan_id)
        package = params.get("package", subscribe_info.package)
        coupon_code = params.get("coupon_code", "")
        method = params.get("method", -1)
        if method <= 0:
            methods = renewal.get_payment_method(
                domain=domain, cookies=cookies, authorization=authorization
            )
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

        renew = params.get("renew", True)
        if renew and subscribe_info.reset_enable and subscribe_info.used_rate >= 0.8:
            success = renewal.flow(
                domain=domain,
                params=payload,
                reset=True,
                cookies=cookies,
                authorization=authorization,
            )
            print(
                "reset {}, domain: {}".format("success" if success else "fail", domain)
            )
        else:
            print(
                f"skip reset traffic plan, domain: {domain}\trenew: {renew}\tenable: {subscribe_info.reset_enable}\tused-rate: {subscribe_info.used_rate}"
            )
        if renew and subscribe_info.renew_enable and subscribe_info.expired_days <= 5:
            success = renewal.flow(
                domain=domain,
                params=payload,
                reset=False,
                cookies=cookies,
                authorization=authorization,
            )
            print(
                "renew {}, domain: {}".format("success" if success else "fail", domain)
            )
        else:
            print(
                f"skip renew traffic plan, domain: {domain}\trenew: {renew}\tenable: {subscribe_info.renew_enable}\texpired-days: {subscribe_info.expired_days}"
            )

        return subscribe_info.token
    except:
        traceback.print_exc()
        return ""


def load_configs(file: str, url: str) -> tuple[list, dict, dict, dict, int]:
    def parse_config(config: dict) -> None:
        sites.extend(config.get("domains", []))
        push_conf.update(config.get("push", {}))
        update_conf.update(config.get("update", {}))
        nonlocal delay
        delay = min(delay, max(config.get("delay", sys.maxsize), 50))

        spiders = config.get("spiders", {})
        crawl_conf.update(spiders)
        telegram_conf = spiders.get("telegram", {})
        disable = telegram_conf.get("disable", False)
        users = telegram_conf.get("users", {})
        period = max(telegram_conf.get("period", 7), 7)
        if not disable and users:
            telegram_conf = params.get("telegram", {})
            enabled_users = telegram_conf.get("users", {})
            telegram_conf["period"] = max(telegram_conf.get("period", 7), period)
            for k, v in users.items():
                include = v.get("include", "")
                exclude = v.get("exclude", "")
                pts = v.get("push_to", [])

                user = enabled_users.get(k, {})
                user["include"] = "|".join(
                    [user.get("include", ""), include]
                ).removeprefix("|")
                user["exclude"] = "|".join(
                    [user.get("exclude", ""), exclude]
                ).removeprefix("|")
                array = user.get("push_to", [])
                array.extend(pts)
                user["push_to"] = list(set(array))

                enabled_users[k] = user
            telegram_conf["users"] = enabled_users
            params["telegram"] = telegram_conf

        google_conf = spiders.get("google", {})
        disable = google_conf.get("disable", False)
        push_to = list(set(google_conf.get("push_to", [])))
        if not disable and push_to:
            pts = params.get("google", [])
            pts.extend(push_to)
            params["google"] = list(set(pts))

        github_conf = spiders.get("github", {})
        disable = github_conf.get("disable", False)
        push_to = list(set(github_conf.get("push_to", [])))
        pages = github_conf.get("pages", 3)
        exclude = github_conf.get("exclude", "")

        if not disable and push_to:
            github_conf = params.get("github", {})
            github_conf["pages"] = max(pages, github_conf.get("pages", 3))
            github_conf["exclude"] = "|".join([exclude, github_conf.get("exclude", "")])
            pts = github_conf.get("push_to", [])
            pts.extend(push_to)
            github_conf["push_to"] = list(set(pts))
            params["github"] = github_conf

        repositories = spiders.get("repositories", [])
        repo_conf = params.get("repositories", {})
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
        params["repositories"] = repo_conf

    sites, delay = [], sys.maxsize
    params, push_conf, crawl_conf, update_conf = {}, {}, {}, {}

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
        if params:
            result = crawl.batch_crawl(conf=params)
            sites.extend(result)
    except:
        print("occur error when load task config")

    return sites, push_conf, crawl_conf, update_conf, delay


def dedup_task(tasks: list) -> list:
    if not tasks:
        return []
    items = []
    for task in tasks:
        if not isinstance(task, TaskConfig):
            print(f"[DedupError] need type 'TaskConfig' but got type '{type(task)}'")
            continue

        found = False
        for item in items:
            if task.sub != "":
                if task.sub == item.sub:
                    found = True
            else:
                if task.domain == item.domain and task.index == item.index:
                    found = True

            if found:
                if not item.rename:
                    item.rename = task.rename
                if task.exclude:
                    item.exclude = "|".join([item.exclude, task.exclude]).removeprefix(
                        "|"
                    )
                if task.include:
                    item.include = "|".join([item.include, task.include]).removeprefix(
                        "|"
                    )

                break

        if not found:
            items.append(task)

    return items


def merge_config(configs: list) -> list:
    def judge_exists(raw: dict, target: dict) -> bool:
        if not raw or not target:
            return False

        rsub = raw.get("sub").strip()
        tsub = target.get("sub", "")
        if not tsub:
            if rsub:
                return False
            return raw.get("domain", "").strip() == target.get("domain", "").strip()
        if isinstance(tsub, str):
            return rsub == tsub.strip()
        for sub in tsub:
            if rsub == sub.strip():
                return True
        return False

    if not configs:
        return []
    items = []
    for conf in configs:
        if not isinstance(conf, dict):
            print(f"[MergeError] need type 'dict' but got type '{type(conf)}'")
            continue

        sub = conf.get("sub", "")
        if isinstance(sub, list) and len(sub) <= 1:
            sub = sub[0] if sub else ""

        # 人工维护配置，无需合并
        if isinstance(sub, list) or conf.get("renew", {}):
            items.append(conf)
            continue

        found = False
        conf["sub"] = sub
        for item in items:
            found = judge_exists(raw=conf, target=item)
            if found:
                if conf.get("errors", 0) > item.get("errors", 0):
                    item["errors"] = conf.get("errors", 0)
                if item.get("debut", False):
                    item["debut"] = conf.get("debut", False)
                if not item.get("rename", ""):
                    item["rename"] = conf.get("rename", "")
                if conf.get("exclude", ""):
                    item["exclude"] = "|".join(
                        [item.get("exclude", ""), conf.get("exclude", "")]
                    ).removeprefix("|")
                if conf.get("include", ""):
                    item["include"] = "|".join(
                        [item.get("include", ""), conf.get("include", "")]
                    ).removeprefix("|")

                break

        if not found:
            items.append(conf)

    return items


def assign(
    sites: list,
    retry: int,
    bin_name: str,
    remain: bool,
    params: dict = {},
) -> tuple[dict, list]:
    jobs, arrays = {}, []
    retry = max(1, retry)
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

        need_verify = site.get("need_verify", False)
        push_names = site.get("push_to", [])
        errors = max(site.get("errors", 0), 0) + 1
        source = site.get("origin", "")
        rename = site.get("rename", "")
        exclude = site.get("exclude", "").strip()
        include = site.get("include", "").strip()
        if not source:
            source = Origin.TEMPORARY.name if not domain else Origin.OWNED.name
        site["origin"] = source
        if source != Origin.TEMPORARY.name:
            site["errors"] = errors
        site["name"] = name.rsplit(crawl.SEPARATOR, maxsplit=1)[0]
        arrays.append(site)

        renews = copy.deepcopy(site.get("renew", {}))
        accounts = renews.pop("account", [])

        # 如果renew不为空，num为配置的renew账号数
        num = len(accounts) if accounts else num

        if (
            site.get("disable", False)
            or "" == name
            or ("" == domain and not subscribes)
            or num <= 0
        ):
            continue

        for idx, push_name in enumerate(push_names):
            if not params.get(push_name, None):
                print(f"cannot found push config, name=[{push_name}]\tsite=[{name}]")
                continue

            flag = True if idx == 0 else False
            tasks = jobs.get(push_name, [])

            for i in range(num):
                index = -1 if num == 1 else i + 1
                sub = subscribes[i] if subscribes else ""
                renew = {}
                if accounts:
                    renew.update(accounts[i])
                    renew.update(renews)
                    renew["renew"] = flag

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
                        need_verify=need_verify,
                        renew=renew,
                        rename=rename,
                        exclude=exclude,
                        include=include,
                    )
                )

            jobs[push_name] = tasks

    if remain and params:
        for k, v in params.items():
            tasks = jobs.get(k, [])
            folderid = v.get("folderid", "").strip()
            fileid = v.get("fileid", "").strip()
            username = v.get("username", "").strip()
            if not folderid or not fileid or not username:
                continue

            subscribes = f"https://paste.gg/p/{username}/{folderid}/files/{fileid}/raw"
            tasks.append(
                TaskConfig(
                    name="remains",
                    domain="",
                    sub=subscribes,
                    index=-1,
                    retry=retry,
                    rate=rate,
                    bin_name=bin_name,
                    tag="R",
                    need_verify=False,
                    renew={},
                    rename="",
                    exclude="",
                    include="",
                )
            )
            jobs[k] = tasks
    return jobs, arrays


def refresh(config: dict, alives: dict, filepath: str = "") -> None:
    if not config:
        print("[UpdateError] cannot update remote config because content is empty")
        return

    update_conf = config.get("update", {})
    if not update_conf.get("enable", False):
        print("[UpdateError] skip update remote config because enable=[False]")
        return

    if not push.validate(push_conf=update_conf):
        print(f"[UpdateError] update config is invalidate")
        return

    domains = merge_config(configs=config.get("domains", []))
    if alives:
        sites = []
        for item in domains:
            source = item.get("origin", "")
            sub = item.get("sub", "")
            if isinstance(sub, list) and len(sub) <= 1:
                sub = sub[0] if sub else ""
            if (
                source in [Origin.TEMPORARY.name, Origin.OWNED.name]
                or isinstance(sub, list)
                or alives.get(sub, False)
            ):
                item.pop("errors", None)
                item.pop("debut", None)
                sites.append(item)
                continue

            errors = item.get("errors", 1)
            expire = Origin.get_expire(source)
            if errors < expire and not item.get("debut", False):
                item.pop("debut", None)
                sites.append(item)

        config["domains"] = sites
        domains = config.get("domains", [])

    if not domains:
        print("[UpdateError] skip update remote config because domians is empty")
        return

    content = json.dumps(config)
    if filepath:
        directory = os.path.abspath(os.path.dirname(filepath))
        os.makedirs(directory, exist_ok=True)
        with open(filepath, "w+", encoding="UTF8") as f:
            f.write(content)
            f.flush()

    push.push_to(content=content, push_conf=update_conf, group="update")


def aggregate(args: argparse.Namespace):
    if not args:
        return

    clash_bin, subconverter_bin = clash.which_bin()

    sites, push_configs, crawl_conf, update_conf, delay = load_configs(
        file=args.file, url=args.server
    )
    push_configs = push.filter_push(push_configs)
    tasks, sites = assign(sites, 3, subconverter_bin, args.remain, push_configs)
    if not tasks:
        print("cannot found any valid config, exit")
        sys.exit(0)
    with multiprocessing.Manager() as manager:
        subscribes = manager.dict()

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
                        subscribes,
                    ),
                )
                p.start()
                processes.append(p)
            for p in processes:
                p.join()

            time.sleep(random.randint(3, 6))
            if len(alive) <= 0:
                print(f"cannot fetch any proxy, group=[{k}]")
                continue

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

        config = {
            "domains": sites,
            "spiders": crawl_conf,
            "push": push_configs,
            "update": update_conf,
        }

        refresh(config=config, alives=dict(subscribes), filepath="")


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
