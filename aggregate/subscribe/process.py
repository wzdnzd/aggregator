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
import workflow
from logger import logger
from origin import Origin
from workflow import TaskConfig

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


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
            github_conf["exclude"] = "|".join(
                [github_conf.get("exclude", ""), exclude]
            ).removeprefix("|")
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
            exclude = repo.get("exclude", "").strip()

            if disable or not username or not repo_name:
                continue
            key = "/".join([username, repo_name])
            item = repo_conf.get(key, {})
            item["username"] = username
            item["repo_name"] = repo_name
            item["commits"] = max(commits, item.get("commits", 3))
            item["exclude"] = "|".join([item.get("exclude", ""), exclude]).removeprefix(
                "|"
            )
            pts = item.get("push_to", [])
            pts.extend(push_to)
            item["push_to"] = list(set(push_to))

            repo_conf[key] = item
        params["repositories"] = repo_conf

        pages = spiders.get("pages", [])
        pages_conf = params.get("pages", {})
        for page in pages:
            disable = page.get("disable", False)
            url = page.get("url", "")
            if disable or not url:
                continue

            push_to = list(set(page.get("push_to", [])))
            exclude = page.get("exclude", "").strip()

            item = pages_conf.get(url, {})
            item["exclude"] = "|".join([item.get("exclude", ""), exclude]).removeprefix(
                "|"
            )
            pts = item.get("push_to", [])
            pts.extend(push_to)
            item["push_to"] = list(set(push_to))
            pages_conf[url] = item

        params["pages"] = pages_conf

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
                logger.error(f"cannot fetch config from remote, url: {url}")
            else:
                parse_config(json.loads(content))

        # 从telegram抓取订阅信息
        if params:
            result = crawl.batch_crawl(conf=params)
            sites.extend(result)
    except:
        logger.error("occur error when load task config")

    return sites, push_conf, crawl_conf, update_conf, delay


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
        push_names = site.get("push_to", [])
        errors = max(site.get("errors", 0), 0) + 1
        source = site.get("origin", "")
        rename = site.get("rename", "")
        exclude = site.get("exclude", "").strip()
        include = site.get("include", "").strip()
        liveness = site.get("liveness", True)
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
                logger.error(
                    f"cannot found push config, name=[{push_name}]\tsite=[{name}]"
                )
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
                        renew=renew,
                        rename=rename,
                        exclude=exclude,
                        include=include,
                        liveness=liveness,
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
                    sub=subscribes,
                    index=-1,
                    retry=retry,
                    rate=rate,
                    bin_name=bin_name,
                    tag="R",
                )
            )
            jobs[k] = tasks
    return jobs, arrays


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
        logger.error("cannot found any valid config, exit")
        sys.exit(0)
    with multiprocessing.Manager() as manager:
        subscribes = manager.dict()

        for k, v in tasks.items():
            v = workflow.dedup_task(v)
            if not v:
                logger.error(f"task is empty, group=[{k}]")
                continue

            logger.info(f"start generate subscribes information, group=[{k}]")
            generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
            if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
                os.remove(generate_conf)

            cpu_count = multiprocessing.cpu_count()
            num = len(v) if len(v) <= cpu_count else cpu_count

            pool = multiprocessing.Pool(num)
            results = pool.map(workflow.execute, v)
            pool.close()

            proxies = list(itertools.chain.from_iterable(results))
            if len(proxies) == 0:
                logger.error(f"exit because cannot fetch any proxy node, group=[{k}]")
                continue

            workspace = os.path.join(PATH, "clash")
            binpath = os.path.join(workspace, clash_bin)
            filename = "config.yaml"
            proxies = clash.generate_config(workspace, proxies, filename)

            # 过滤出需要检查可用性的节点
            checks, nochecks = workflow.liveness_fillter(proxies=proxies)
            if checks:
                utils.chmod(binpath)
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

                logger.info(
                    f"clash start success, begin check proxies, num: {len(checks)}"
                )

                processes = []
                semaphore = multiprocessing.Semaphore(args.num)
                time.sleep(random.randint(3, 5))

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
                            subscribes,
                        ),
                    )
                    p.start()
                    processes.append(p)
                for p in processes:
                    p.join()

                nochecks.extend(list(availables))

            if len(nochecks) <= 0:
                logger.error(f"cannot fetch any proxy, group=[{k}]")
                continue

            data = {"proxies": nochecks}
            source_file = "config.yaml"
            filepath = os.path.join(PATH, "subconverter", source_file)
            with open(filepath, "w+", encoding="utf8") as f:
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
                logger.error(f"cannot generate subconverter config file, group=[{k}]")
                continue

            if subconverter.convert(binname=subconverter_bin, artifact=artifact):
                # 推送到https://paste.gg
                filepath = os.path.join(PATH, "subconverter", dest_file)
                push.push_file(filepath, push_configs.get(k, {}), k)

            # 关闭clash
            workflow.cleanup(
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

        workflow.refresh(config=config, alives=dict(subscribes), filepath="")


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
