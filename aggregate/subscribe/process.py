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
from copy import deepcopy

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


def load_configs(url: str) -> tuple[list, dict, dict, dict, int]:
    def parse_config(config: dict) -> None:
        sites.extend(config.get("domains", []))
        push_conf.update(config.get("push", {}))
        update_conf.update(config.get("update", {}))
        crawl_conf.update(config.get("crawl", {}))

        nonlocal delay
        delay = min(delay, max(config.get("delay", sys.maxsize), 50))

        # global exclude
        params["exclude"] = crawl_conf.get("exclude", "")
        spiders = deepcopy(crawl_conf)

        # spider's config for telegram
        telegram_conf = spiders.get("telegram", {})
        users = telegram_conf.pop("users", {})
        telegram_conf["pages"] = max(telegram_conf.get("pages", 1), 1)
        if telegram_conf.pop("enable", True) and users:
            enabled_users, common_exclude = {}, telegram_conf.pop("exclude", "")
            for k, v in users.items():
                exclude = v.get("exclude", "").strip()
                v["exclude"] = (
                    f"{exclude}|{common_exclude}".removeprefix("|")
                    if common_exclude
                    else exclude
                )
                v["push_to"] = list(set(v.get("push_to", [])))

                enabled_users[k] = v
            telegram_conf["users"] = enabled_users
            params["telegram"] = telegram_conf

        # spider's config for google
        google_conf = spiders.get("google", {})
        push_to = list(set(google_conf.get("push_to", [])))
        if google_conf.pop("enable", True) and push_to:
            google_conf["push_to"] = push_to
            params["google"] = google_conf

        # spider's config for github
        github_conf = spiders.get("github", {})
        push_to = list(set(github_conf.get("push_to", [])))
        if github_conf.pop("enable", True) and push_to:
            github_conf["pages"] = max(github_conf.get("pages", 3), 3)
            github_conf["push_to"] = push_to
            params["github"] = github_conf

        # spider's config for github's repositories
        repo_conf, repositories = spiders.get("repositories", []), {}
        for repo in repo_conf:
            enable = repo.pop("enable", True)
            username = repo.get("username", "").strip()
            repo_name = repo.get("repo_name", "").strip()
            if not enable or not username or not repo_name:
                continue

            key = "/".join([username, repo_name])
            push_to = list(set(repo.get("push_to", [])))
            repo["username"] = username
            repo["repo_name"] = repo_name
            repo["commits"] = max(repo.get("commits", 3), 1)
            repo["push_to"] = push_to

            repositories[key] = repo
        params["repositories"] = repositories

        # spider's config for specified page
        pages_conf, pages = spiders.get("pages", []), {}
        for page in pages_conf:
            enable = page.pop("enable", True)
            url = page.get("url", "")
            push_to = list(set(page.get("push_to", [])))
            if not enable or not url or not push_to:
                continue

            page["push_to"] = push_to
            pages[url] = page

        params["pages"] = pages

        # spider's config for scripts
        scripts_conf, scripts = spiders.get("scripts", []), {}

        for script in scripts_conf:
            enable = script.pop("enable", True)
            path = script.pop("script", "").strip()
            if not enable or not path:
                continue

            scripts[path] = script.get("params", {})
        params["scripts"] = scripts

    sites, delay = [], sys.maxsize
    params, push_conf, crawl_conf, update_conf = {}, {}, {}, {}

    try:
        if re.match(
            "^(https?:\/\/(([a-zA-Z0-9]+-?)+[a-zA-Z0-9]+\.)+[a-zA-Z]+)(:\d+)?(\/.*)?(\?.*)?(#.*)?$",
            url,
        ):
            headers = {"User-Agent": utils.USER_AGENT, "Referer": url}
            content = utils.http_get(url=url, headers=headers)
            if not content:
                logger.error(f"cannot fetch config from remote, url: {url}")
            else:
                parse_config(json.loads(content))
        elif os.path.exists(url) and os.path.isfile(url):
            config = json.loads(open(url, "r", encoding="utf8").read())
            parse_config(config)

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
    pushtool: push.PushTo,
    push_conf: dict = {},
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
            not site.get("enable", True)
            or "" == name
            or ("" == domain and not subscribes)
            or num <= 0
        ):
            continue

        for idx, push_name in enumerate(push_names):
            if not push_conf.get(push_name, None):
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
                    renew["enable"] = flag

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

    if remain and push_conf:
        for k, v in push_conf.items():
            tasks = jobs.get(k, [])
            folderid = v.get("folderid", "").strip()
            fileid = v.get("fileid", "").strip()
            username = v.get("username", "").strip()
            subscribes = pushtool.raw_url(
                fileid=fileid, folderid=folderid, username=username
            )
            if not subscribes:
                continue

            tasks.append(
                TaskConfig(
                    name="remains",
                    sub=subscribes,
                    index=-1,
                    retry=retry,
                    rate=rate,
                    bin_name=bin_name,
                )
            )
            jobs[k] = tasks
    return jobs, arrays


def aggregate(args: argparse.Namespace):
    if not args:
        return

    pushtool = push.get_instance(push_type=1)
    clash_bin, subconverter_bin = clash.which_bin()

    sites, push_configs, crawl_conf, update_conf, delay = load_configs(url=args.server)
    push_configs = pushtool.filter_push(push_configs)
    tasks, sites = assign(
        sites=sites,
        retry=3,
        bin_name=subconverter_bin,
        remain=args.remain,
        pushtool=pushtool,
        push_conf=push_configs,
    )
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
                    f"clash start success, begin check proxies, count: {len(checks)}"
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

            logger.info(f"proxies check finished, count: {len(nochecks)}\tgroup: {k}")

            data = {"proxies": nochecks}
            push_conf = push_configs.get(k, {})
            if push_conf.get("target") in ["v2ray", "mixed"]:
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
                    logger.error(
                        f"cannot generate subconverter config file, group=[{k}]"
                    )
                    continue

                if subconverter.convert(binname=subconverter_bin, artifact=artifact):
                    # 推送到远端
                    filepath = os.path.join(PATH, "subconverter", dest_file)
                    pushtool.push_file(filepath=filepath, push_conf=push_conf, group=k)
                # 关闭clash
                workflow.cleanup(
                    process,
                    os.path.join(PATH, "subconverter"),
                    [source_file, dest_file, "generate.ini"],
                )
            else:
                content = yaml.dump(data=data, allow_unicode=True)
                pushtool.push_to(content=content, push_conf=push_conf, group=k)
                workflow.cleanup(process)

        config = {
            "domains": sites,
            "spiders": crawl_conf,
            "push": push_configs,
            "update": update_conf,
        }

        workflow.refresh(
            config=config, push=pushtool, alives=dict(subscribes), filepath=""
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
