# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import argparse
import base64
import copy
import itertools
import json
import os
import random
import re
import subprocess
import sys
import time
from copy import deepcopy
from dataclasses import dataclass, field

import crawl
import executable
import location
import push
import utils
import workflow
import yaml
from airport import AirPort
from logger import logger
from origin import Origin
from workflow import TaskConfig

import clash
import subconverter

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


@dataclass
class ProcessConfig(object):
    # task list
    tasks: list[dict] = field(default_factory=list)

    # crawl config
    crawl: dict = field(default_factory=dict)

    # persist config
    storage: dict = field(default_factory=dict)

    # groups config
    groups: dict[dict] = field(default_factory=dict)

    # update config
    update: dict = field(default_factory=dict)

    # max acceptable delay
    delay: int = 5000


def load_configs(
    url: str,
    only_check: bool = False,
    num_threads: int = 0,
    display: bool = True,
) -> ProcessConfig:
    def parse_config(config: dict) -> None:
        tasks.extend(config.get("domains", []))
        groups.update(config.get("groups", {}))
        update_conf.update(config.get("update", {}))
        crawl_conf.update(config.get("crawl", {}))
        storage.update(config.get("storage", {}))

        nonlocal engine
        engine = utils.trim(storage.get("engine", "")) or engine

        nonlocal delay
        delay = min(delay, max(config.get("delay", sys.maxsize), 50))

        if only_check:
            return

        # global exclude
        params["exclude"] = crawl_conf.get("exclude", "")

        # persistence configuration
        persist = {k: storage.get("items", {}).get(v, {}) for k, v in crawl_conf.get("persist", {}).items()}
        persist["engine"] = engine
        params["persist"] = persist

        params["config"] = crawl_conf.get("config", {})
        params["enable"] = crawl_conf.get("enable", True)
        params["singlelink"] = crawl_conf.get("singlelink", False)

        threshold = max(crawl_conf.get("threshold", 1), 1)
        params["threshold"] = threshold
        spiders = deepcopy(crawl_conf)

        # spider's config for telegram
        telegram_conf = spiders.get("telegram", {})
        users = telegram_conf.pop("users", {})
        telegram_conf["pages"] = max(telegram_conf.get("pages", 1), 1)
        if telegram_conf.pop("enable", True) and users:
            enabled_users, common_exclude = {}, telegram_conf.pop("exclude", "")
            for k, v in users.items():
                exclude = v.get("exclude", "").strip()
                v["exclude"] = f"{exclude}|{common_exclude}".removeprefix("|") if common_exclude else exclude
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

        # spider's config for yandex
        yandex_conf = spiders.get("yandex", {})
        push_to = list(set(yandex_conf.get("push_to", [])))
        if yandex_conf.pop("enable", True) and push_to:
            yandex_conf["push_to"] = push_to
            params["yandex"] = yandex_conf

        # spider's config for github
        github_conf = spiders.get("github", {})
        push_to = list(set(github_conf.get("push_to", [])))
        spams = list(set(github_conf.get("spams", [])))
        if github_conf.pop("enable", True) and push_to:
            github_conf["pages"] = max(github_conf.get("pages", 1), 1)
            github_conf["push_to"] = push_to
            github_conf["spams"] = spams
            params["github"] = github_conf

        # spider's config for twitter
        twitter_conf = spiders.get("twitter", {})
        users = twitter_conf.pop("users", {})
        if twitter_conf.pop("enable", True) and users:
            enabled_users = {}
            for k, v in users.items():
                if utils.isblank(k) or not v or type(v) != dict or not v.pop("enable", True):
                    continue

                v["push_to"] = list(set(v.get("push_to", [])))
                enabled_users[k] = v

            params["twitter"] = enabled_users

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

            multiple = page.pop("multiple", False)
            if not multiple:
                page["push_to"] = push_to
                if isinstance(url, str):
                    pages[url] = page
                elif isinstance(url, list):
                    for u in url:
                        u = utils.trim(u)
                        if u:
                            pages[u] = page
            else:
                placeholder = utils.trim(page.pop("placeholder", ""))
                if not placeholder or placeholder not in url or not isinstance(url, str):
                    continue

                # page number range
                start, end = -1, -1
                try:
                    start = int(page.pop("start", 1))
                    end = int(page.pop("end", 1))
                except:
                    pass

                if start < 0 or end < start:
                    continue

                for i in range(start, end + 1):
                    copypage = deepcopy(page)
                    link = url.replace(placeholder, str(i))
                    copypage["url"] = link
                    copypage["push_to"] = push_to
                    pages[link] = copypage

        params["pages"] = pages

        # spider's config for scripts
        scripts_conf, scripts = spiders.get("scripts", []), {}

        for script in scripts_conf:
            enable = script.pop("enable", True)
            path = script.pop("script", "").strip()
            if not enable or not path:
                continue

            task_conf = script.get("params", {})
            if not isinstance(task_conf, dict):
                task_conf = {}

            # record storge engine
            task_conf["engine"] = engine

            scripts[path] = task_conf
        params["scripts"] = scripts

    def verify(storage: dict, groups: dict) -> bool:
        if not isinstance(storage, dict) or not isinstance(groups, dict):
            return False

        pushtool = push.get_instance(engine=storage.get("engine", ""))
        if not isinstance(storage.get("items", {}), dict):
            logger.error(f"cannot found any valid storage config")
            return False

        items = pushtool.filter_push(push_conf=storage.get("items", {}))
        for name, group in groups.items():
            name = utils.trim(name)

            if not name or not isinstance(group, dict):
                logger.error(f"invalid group config, name: {name}")
                return False

            targets = group.get("targets", {})
            if not targets or not isinstance(targets, dict):
                logger.error(f"group {name} should contain at least one type conversion")
                return False

            for category, storage_name in targets.items():
                category = utils.trim(category).lower()
                if category not in subconverter.CONVERT_TARGETS:
                    logger.error(f"group {name} contains unsupported conversion type: {category}")
                    return False

                storage_name = utils.trim(storage_name)
                if storage_name not in items:
                    logger.error(f"missing storage configuration for group {name} to convert type to {category}")
                    return False

        return True

    tasks, delay = [], sys.maxsize
    engine, storage, groups = "", {}, {}
    params, crawl_conf, update_conf = {}, {}, {}

    try:
        if re.match(
            r"^(https?:\/\/(([a-zA-Z0-9]+-?)+[a-zA-Z0-9]+\.)+[a-zA-Z]+)(:\d+)?(\/.*)?(\?.*)?(#.*)?$",
            url,
        ):
            headers = {"User-Agent": utils.USER_AGENT, "Referer": url}
            content = utils.http_get(url=url, headers=headers)
            if not content:
                logger.error(f"cannot fetch config from remote, url: {utils.hide(url=url)}")
            else:
                os.environ["SUBSCRIBE_CONF"] = url
                parse_config(json.loads(content))
        else:
            localfile = os.path.abspath(url)
            if os.path.exists(localfile) and os.path.isfile(localfile):
                config = json.loads(open(localfile, "r", encoding="utf8").read())
                os.environ["SUBSCRIBE_CONF"] = localfile
                parse_config(config)

        # check configuration
        if not verify(storage=storage, groups=groups):
            raise ValueError(f"there are some errors in the configuration, please check and confirm")

        # execute crawl tasks
        if params:
            result = crawl.batch_crawl(conf=params, num_threads=num_threads, display=display)
            tasks.extend(result)
    except SystemExit as e:
        if e.code != 0:
            logger.error("parse configuration failed due to process abnormally exits")

        sys.exit(e.code)
    except:
        logger.error("occur error when load task config")
        sys.exit(0)

    return ProcessConfig(
        tasks=tasks,
        crawl=crawl_conf,
        storage=storage,
        groups=groups,
        update=update_conf,
        delay=delay,
    )


def assign(
    pc: ProcessConfig,
    retry: int,
    bin_name: str,
    remain: bool,
    pushtool: push.PushTo,
    only_check=False,
    rigid: bool = True,
) -> tuple[list[TaskConfig], dict, list]:
    if not isinstance(pc, ProcessConfig):
        return [], {}, []

    tasks, groups, arrays = [], {}, []
    retry, globalid = max(1, retry), 0

    # 是否允许特殊协议
    special_protocols = AirPort.enable_special_protocols()

    sites = [] if not isinstance(pc.tasks, list) else deepcopy(pc.tasks)
    for site in sites:
        if not site:
            continue

        name = site.get("name", "").strip().lower()
        domain = site.get("domain", "").strip().lower()

        # 订阅地址，支持单个或多个
        subscribe = site.get("sub", "")
        if isinstance(subscribe, str):
            subscribe = [subscribe.strip()]
        subscribe = [s for s in subscribe if s.strip() != ""]
        if len(subscribe) >= 2:
            subscribe = list(set(subscribe))

        # 自定义标签，追加到名称前
        tag = site.get("tag", "").strip().upper()

        # 节点倍率超过该值将会被丢弃
        rate = float(site.get("rate", 3.0))

        # 需要注册账号的个数
        num = min(max(1, int(site.get("count", 1))), 10)

        # 如果订阅链接不为空，num为订阅链接数
        num = len(subscribe) if subscribe else num

        # 组名列表
        push_names = site.get("push_to", [])

        # 失败次数，超过该值将不再尝试注册
        errors = max(site.get("errors", 0), 0) + 1

        # 来源类别
        source = site.get("origin", "")

        # 重命名规则，正常正则表达式
        rename = site.get("rename", "")

        # 排除匹配到的节点，支持正则表达式
        exclude = site.get("exclude", "").strip()

        # 仅保留匹配到的节点，支持正则表达式
        include = site.get("include", "").strip()

        # 是否检查 ChatGPT 的连通性
        chatgpt = site.get("chatgpt", {})

        # 是否对节点测活
        liveness = site.get("liveness", True)

        # 拒绝跳过证书验证
        disable_insecure = site.get("secure", False)

        # 优惠码
        coupon = utils.trim(site.get("coupon", ""))

        # 邀请码
        invite_code = utils.trim(site.get("invite_code", ""))

        # 覆盖subconverter默认exclude规则
        ignoreder = site.get("ignorede", False)

        # 需要人机验证时是否直接放弃
        chuck = site.get("chuck", False)

        # 接口地址前缀
        api_prefix = site.get("api_prefix", "")

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

        if not site.get("enable", True) or "" == name or ("" == domain and not subscribe) or num <= 0:
            continue

        for i in range(num):
            index = -1 if num == 1 else i + 1
            sub = subscribe[i] if subscribe else ""
            renew = {"coupon_code": coupon} if coupon else {}

            globalid += 1
            if accounts:
                renew.update(accounts[i])
                renew.update(renews)

            if renew and api_prefix:
                renew["api_prefix"] = api_prefix

            task = TaskConfig(
                name=name,
                taskid=globalid,
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
                chatgpt=chatgpt,
                liveness=liveness,
                coupon=coupon,
                disable_insecure=disable_insecure,
                ignorede=ignoreder,
                rigid=rigid,
                chuck=chuck,
                special_protocols=special_protocols,
                invite_code=invite_code,
                api_prefix=api_prefix,
            )
            found = workflow.exists(tasks=tasks, task=task)
            if found:
                continue

            tasks.append(task)
            for push_name in push_names:
                if push_name not in pc.groups:
                    logger.error(f"cannot found push config, name=[{push_name}]\tsite=[{name}]")
                    continue

                taskids = groups.get(push_name, [])
                taskids.append(globalid)
                groups[push_name] = taskids

    if (remain or only_check) and pc.groups:
        if only_check:
            # clean all extra tasks
            tasks, groups, globalid = [], {k: [] for k in groups.keys()}, 0

        for k, v in pc.groups.items():
            taskids = groups.get(k, [])
            targets = v.get("targets", {})
            if not targets:
                continue

            # get the first conversion configuration for each group
            push_conf = pc.storage.get("items", {}).get(targets.values()[0], {})
            subscribe = pushtool.raw_url(push_conf=push_conf)
            if k not in groups or not subscribe:
                continue

            globalid += 1
            tasks.append(
                TaskConfig(
                    name=f"remains-{k}",
                    taskid=globalid,
                    sub=subscribe,
                    index=-1,
                    retry=retry,
                    bin_name=bin_name,
                    special_protocols=special_protocols,
                )
            )
            taskids.append(globalid)
            groups[k] = taskids
    return tasks, groups, arrays


def aggregate(args: argparse.Namespace) -> None:
    if not args or not isinstance(args, argparse.Namespace):
        return

    clash_bin, subconverter_bin = executable.which_bin()
    display = not args.invisible

    # parse config
    server = utils.trim(args.server) or os.environ.get("SUBSCRIBE_CONF", "").strip()
    process_config = load_configs(
        url=server,
        only_check=args.check,
        num_threads=args.num,
        display=display,
    )

    storages = process_config.storage or {}
    pushtool = push.get_instance(engine=storages.get("engine", ""))
    retry = min(max(1, args.retry), 10)

    # generate tasks
    tasks, groups, sites = assign(
        pc=process_config,
        retry=retry,
        bin_name=subconverter_bin,
        remain=not args.overwrite,
        pushtool=pushtool,
        only_check=args.check,
        rigid=not args.flexible,
    )
    if not tasks:
        logger.error("cannot found any valid config, exit")
        sys.exit(0)

    # fetch all subscriptions
    generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
    if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
        os.remove(generate_conf)

    logger.info(f"start fetch all subscriptions, count: [{len(tasks)}]")
    results = utils.multi_process_run(func=workflow.executewrapper, tasks=tasks)

    subscribes, datasets = {}, {}
    for i in range(len(results)):
        data = results[i]
        if not data or data[0] < 0 or not data[1]:
            # not contain any proxy
            if tasks[i] and tasks[i].sub:
                subscribes[tasks[i].sub] = False
            continue

        datasets[data[0]] = data[1]

    for k, v in groups.items():
        if not v:
            logger.error(f"task is empty, group=[{k}]")
            continue

        arrays = [datasets.get(x, []) for x in v]
        proxies = list(itertools.chain.from_iterable(arrays))
        if len(proxies) == 0:
            logger.error(f"exit because cannot fetch any proxy node, group=[{k}]")
            continue

        workspace = os.path.join(PATH, "clash")
        binpath = os.path.join(workspace, clash_bin)
        filename = "config.yaml"
        proxies = clash.generate_config(workspace, proxies, filename)

        # filer
        skip = utils.trim(os.environ.get("SKIP_ALIVE_CHECK", "false")).lower() in ["true", "1"]
        nochecks, starttime = proxies, time.time()

        if not skip:
            checks, nochecks = workflow.liveness_fillter(proxies=proxies)
            if checks:
                # executable
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

                logger.info(f"clash start success, begin check proxies, group: {k}\tcount: {len(checks)}")
                time.sleep(random.randint(5, 8))

                params = [
                    [p, clash.EXTERNAL_CONTROLLER, args.timeout, args.url, process_config.delay, False]
                    for p in checks
                    if isinstance(p, dict)
                ]

                # check
                masks = utils.multi_thread_run(
                    func=clash.check,
                    tasks=params,
                    num_threads=args.num,
                    show_progress=display,
                )

                # close clash client
                try:
                    process.terminate()
                except:
                    logger.error(f"terminate clash process error, group: {k}")

                availables = [checks[i] for i in range(len(checks)) if masks[i]]
                nochecks.extend(availables)

                dead = len(checks) - len(availables)
                logger.info(f"proxies check finished, total: {len(checks)}, alive: {len(availables)}, dead: {dead}")

        for item in nochecks:
            item.pop("sub", "")

        if len(nochecks) <= 0:
            logger.error(f"cannot fetch any proxy, group=[{k}], cost: {time.time()-starttime:.2f}s")
            continue

        group_conf = process_config.groups.get(k, {})
        emoji = group_conf.get("emoji", True)
        list_only = group_conf.get("list", True)

        regularize = group_conf.get("regularize", {})
        if regularize and isinstance(regularize, dict) and regularize.get("enable", False):
            locate = regularize.get("locate", False)
            try:
                bits = max(1, int(regularize.get("bits", 2)))
            except:
                bits = 2

            nochecks = location.regularize(
                proxies=nochecks,
                num_threads=args.num,
                show_progress=display,
                locate=locate,
                digits=bits,
            )

        source_file, data = "config.yaml", {"proxies": nochecks}
        filepath = os.path.join(PATH, "subconverter", source_file)
        with open(filepath, "w+", encoding="utf8") as f:
            yaml.add_representer(clash.QuotedStr, clash.quoted_scalar)
            yaml.dump(data, f, allow_unicode=True)

        targets = group_conf.get("targets", {})
        for target, storage_name in targets.items():
            persisted, content = False, " "

            # convert
            artifact = f"convert_{target}"
            dest_file = subconverter.get_filename(target=target)

            if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
                os.remove(generate_conf)

            success = subconverter.generate_conf(
                filepath=generate_conf,
                name=artifact,
                source=source_file,
                dest=dest_file,
                target=target,
                emoji=emoji,
                list_only=list_only,
            )
            if not success:
                logger.error(f"cannot generate subconverter config file, group: {k}, target: {target}")
                continue

            if subconverter.convert(binname=subconverter_bin, artifact=artifact):
                filepath = os.path.join(PATH, "subconverter", dest_file)

                if not os.path.exists(filepath) or not os.path.isfile(filepath):
                    logger.error(f"converted file {filepath} not found, group: {k}, target: {target}")
                    continue

                with open(filepath, "r", encoding="utf8") as f:
                    content = f.read()

                mixed = target == "v2ray" or target == "mixed" or "ss" in target
                if mixed and not utils.isb64encode(content=content):
                    # base64 encode
                    try:
                        content = base64.b64encode(content.encode(encoding="UTF8")).decode(encoding="UTF8")
                    except Exception as e:
                        logger.error(f"base64 encode error, group: {k}, target: {target}, message: {str(e)}")
                        continue

                # save to remote server
                push_conf = process_config.storage.get("items", {}).get(storage_name, {})
                persisted = pushtool.push_to(content=content, push_conf=push_conf, group=f"{k}::{target}")

            # clean workspace
            workflow.cleanup(os.path.join(PATH, "subconverter"), [dest_file, "generate.ini"])

            if content and not persisted:
                filename = os.path.join(PATH, "data", f"{k}-{dest_file}")

                logger.error(f"storage config to remote failed, group: {k}, target: {target}, save it to {filename}")
                utils.write_file(filename=filename, lines=content)

        workflow.cleanup(os.path.join(PATH, "subconverter"), [source_file])
        cost = "{:.2f}s".format(time.time() - starttime)
        logger.info(f"group [{k}] process finished, count: {len(nochecks)}, cost: {cost}")

    config = {
        "domains": sites,
        "crawl": process_config.crawl,
        "groups": process_config.groups,
        "storage": process_config.storage,
        "update": process_config.update,
    }
    skip_remark = utils.trim(os.environ.get("SKIP_REMARK", "false")).lower() in ["true", "1"]

    workflow.refresh(config=config, push=pushtool, alives=dict(subscribes), skip_remark=skip_remark)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-c",
        "--check",
        dest="check",
        action="store_true",
        default=False,
        help="only check proxies are alive",
    )

    parser.add_argument(
        "-e",
        "--envrionment",
        type=str,
        required=False,
        default=".env",
        help="environment file name",
    )

    parser.add_argument(
        "-f",
        "--flexible",
        dest="flexible",
        action="store_true",
        default=False,
        help="try registering with a gmail alias when you encounter a whitelisted mailbox",
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
        "-n",
        "--num",
        type=int,
        required=False,
        default=64,
        help="threads num for check proxy",
    )

    parser.add_argument(
        "-o",
        "--overwrite",
        dest="overwrite",
        action="store_true",
        default=False,
        help="exclude remains proxies",
    )

    parser.add_argument(
        "-r",
        "--retry",
        type=int,
        required=False,
        default=3,
        help="retry times when http request failed",
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

    args = parser.parse_args()
    utils.load_dotenv(args.envrionment)

    aggregate(args=args)
