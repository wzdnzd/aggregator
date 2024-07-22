# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import argparse
import itertools
import os
import random
import re
import shutil
import subprocess
import sys
import time

import crawl
import executable
import push
import utils
import workflow
import yaml
from airport import AirPort
from logger import logger
from urlvalidator import isurl
from workflow import TaskConfig

import clash
import subconverter

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

DATA_BASE = os.path.join(PATH, "data")


def assign(
    bin_name: str,
    domains_file: str = "",
    overwrite: bool = False,
    pages: int = sys.maxsize,
    rigid: bool = True,
    display: bool = True,
    num_threads: int = 0,
    **kwargs,
) -> list[TaskConfig]:
    def load_exist(username: str, gist_id: str, access_token: str, filename: str) -> list[str]:
        if not filename:
            return []

        subscriptions = set()

        pattern = r"^https?:\/\/[^\s]+"
        local_file = os.path.join(DATA_BASE, filename)
        if os.path.exists(local_file) and os.path.isfile(local_file):
            with open(local_file, "r", encoding="utf8") as f:
                items = re.findall(pattern, str(f.read()), flags=re.M)
                if items:
                    subscriptions.update(items)

        if username and gist_id and access_token:
            push_tool = push.PushToGist(token=access_token)
            url = push_tool.raw_url(push_conf={"username": username, "gistid": gist_id, "filename": filename})

            content = utils.http_get(url=url, timeout=30)
            items = re.findall(pattern, content, flags=re.M)
            if items:
                subscriptions.update(items)

        logger.info("start checking whether existing subscriptions have expired")

        # 过滤已过期订阅并返回
        links = list(subscriptions)
        results = utils.multi_thread_run(
            func=crawl.check_status,
            tasks=links,
            num_threads=num_threads,
            show_progress=display,
        )

        return [links[i] for i in range(len(links)) if results[i][0] and not results[i][1]]

    def parse_domains(content: str) -> dict:
        if not content or not isinstance(content, str):
            logger.warning("cannot found any domain due to content is empty or not string")
            return {}

        records = {}
        for line in content.split("\n"):
            line = utils.trim(line)
            if not line or line.startswith("#"):
                continue

            words = line.rsplit(delimiter, maxsplit=2)
            address = utils.trim(words[0])
            coupon = utils.trim(words[1]) if len(words) > 1 else ""
            invite_code = utils.trim(words[2]) if len(words) > 2 else ""

            records[address] = {"coupon": coupon, "invite_code": invite_code}

        return records

    subscribes_file = utils.trim(kwargs.get("subscribes_file", ""))
    access_token = utils.trim(kwargs.get("access_token", ""))
    gist_id = utils.trim(kwargs.get("gist_id", ""))
    username = utils.trim(kwargs.get("username", ""))
    chuck = kwargs.get("chuck", False)

    # 加载已有订阅
    subscriptions = load_exist(username, gist_id, access_token, subscribes_file)
    logger.info(f"load exists subscription finished, count: {len(subscriptions)}")

    # 是否允许特殊协议
    special_protocols = AirPort.enable_special_protocols()

    tasks = (
        [
            TaskConfig(name=utils.random_chars(length=8), sub=x, bin_name=bin_name, special_protocols=special_protocols)
            for x in subscriptions
            if x
        ]
        if subscriptions
        else []
    )

    # 仅更新已有订阅
    if tasks and kwargs.get("refresh", False):
        logger.info("skip registering new accounts, will use existing subscriptions for refreshing")
        return tasks

    domains, delimiter = {}, "@#@#"
    domains_file = utils.trim(domains_file)
    if not domains_file:
        domains_file = "domains.txt"

    # 加载已有站点列表
    fullpath = os.path.join(DATA_BASE, domains_file)
    if os.path.exists(fullpath) and os.path.isfile(fullpath):
        with open(fullpath, "r", encoding="UTF8") as f:
            domains.update(parse_domains(content=str(f.read())))

    # 爬取新站点列表
    if not domains or overwrite:
        candidates = crawl.collect_airport(
            channel="jichang_list",
            page_num=pages,
            num_thread=num_threads,
            rigid=rigid,
            display=display,
            filepath=os.path.join(DATA_BASE, "coupons.txt"),
            delimiter=delimiter,
            chuck=chuck,
        )

        if candidates:
            for k, v in candidates.items():
                item = domains.get(k, {})
                item["coupon"] = v

                domains[k] = item

            overwrite = True

    # 加载自定义机场列表
    customize_link = utils.trim(kwargs.get("customize_link", ""))
    if customize_link:
        if isurl(customize_link):
            domains.update(parse_domains(content=utils.http_get(url=customize_link)))
        else:
            local_file = os.path.join(DATA_BASE, customize_link)
            if local_file != fullpath and os.path.exists(local_file) and os.path.isfile(local_file):
                with open(local_file, "r", encoding="UTF8") as f:
                    domains.update(parse_domains(content=str(f.read())))

    if not domains:
        logger.error("cannot collect any new airport for free use")
        return tasks

    if overwrite:
        crawl.save_candidates(candidates=domains, filepath=fullpath, delimiter=delimiter)

    for domain, param in domains.items():
        name = crawl.naming_task(url=domain)
        tasks.append(
            TaskConfig(
                name=name,
                domain=domain,
                coupon=param.get("coupon", ""),
                invite_code=param.get("invite_code", ""),
                bin_name=bin_name,
                rigid=rigid,
                chuck=chuck,
                special_protocols=special_protocols,
            )
        )

    return tasks


def aggregate(args: argparse.Namespace) -> None:
    def parse_gist_link(link: str) -> tuple[str, str]:
        # 提取 gist 用户名及 id
        words = utils.trim(link).split("/", maxsplit=1)
        if len(words) != 2:
            logger.error(f"cannot extract username and gist id due to invalid github gist link")
            return "", ""

        return utils.trim(words[0]), utils.trim(words[1])

    clash_bin, subconverter_bin = executable.which_bin()
    display = not args.invisible

    subscribes_file = "subscribes.txt"
    access_token = utils.trim(args.key)
    username, gist_id = parse_gist_link(args.gist)

    tasks = assign(
        bin_name=subconverter_bin,
        domains_file="domains.txt",
        overwrite=args.overwrite,
        pages=args.pages,
        rigid=not args.easygoing,
        display=display,
        num_threads=args.num,
        refresh=args.refresh,
        chuck=args.chuck,
        username=username,
        gist_id=gist_id,
        access_token=access_token,
        subscribes_file=subscribes_file,
        customize_link=args.yourself,
    )

    if not tasks:
        logger.error("cannot found any valid config, exit")
        sys.exit(0)

    # 已有订阅已经做过过期检查，无需再测
    old_subscriptions = set([t.sub for t in tasks if t.sub])

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
        nodes = clash.filter_proxies(proxies).get("proxies", [])
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
        # 移除无用的标记
        p.pop("chatgpt", False)
        p.pop("liveness", True)

        sub = p.pop("sub", "")
        if sub:
            subscriptions.add(sub)

    data = {"proxies": nodes}
    urls = list(subscriptions)

    # 如果文件夹不存在则创建
    os.makedirs(DATA_BASE, exist_ok=True)

    # 保存为 mixed 格式
    to_mixed = args.both or args.mixed

    # 保存为 clash 格式
    to_clash = args.both or not args.mixed

    source, clash_file, mixed_file = "proxies.yaml", "clash.yaml", "v2ray.txt"
    supplier = os.path.join(PATH, "subconverter", source)
    if os.path.exists(supplier) and os.path.isfile(supplier):
        os.remove(supplier)

    with open(supplier, "w+", encoding="utf8") as f:
        yaml.dump(data, f, allow_unicode=True)

    if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
        os.remove(generate_conf)

    targets, records = [], {}
    if to_clash:
        targets.append(("convert_clash", clash_file, "clash", not args.all, args.vitiate))
    if to_mixed:
        targets.append(("convert_mixed", mixed_file, "mixed", False, args.vitiate))

    for t in targets:
        success = subconverter.generate_conf(generate_conf, t[0], source, t[1], t[2], t[3], t[4])
        if not success:
            logger.error(f"cannot generate subconverter config file for target: {t[2]}")
            continue

        if subconverter.convert(binname=subconverter_bin, artifact=t[0]):
            filepath = os.path.join(DATA_BASE, t[1])
            shutil.move(os.path.join(PATH, "subconverter", t[1]), filepath)

            records[t[1]] = filepath

    if len(records) > 0:
        os.remove(supplier)
    else:
        logger.error(f"all targets convert failed, you can view the temporary file: {supplier}")
        sys.exit(1)

    logger.info(f"found {len(nodes)} proxies, save it to {list(records.values())}")

    life, traffic = max(0, args.life), max(0, args.flow)
    if life > 0 or traffic > 0:
        # 过滤出新的订阅并检查剩余流量和过期时间是否满足要求
        new_subscriptions = [x for x in urls if x not in old_subscriptions]

        tasks = [[x, 2, traffic, life, 0, True] for x in new_subscriptions]
        results = utils.multi_thread_run(
            func=crawl.check_status,
            tasks=tasks,
            num_threads=args.num,
            show_progress=display,
        )

        total = len(urls)

        # 筛选出为符合要求的订阅
        urls = [new_subscriptions[i] for i in range(len(new_subscriptions)) if results[i][0] and not results[i][1]]
        discard = len(tasks) - len(urls)

        # 合并新老订阅
        urls.extend(list(old_subscriptions))

        logger.info(f"filter subscriptions finished, total: {total}, found: {len(urls)}, discard: {discard}")

    utils.write_file(filename=os.path.join(DATA_BASE, subscribes_file), lines=urls)
    domains = [utils.extract_domain(url=x, include_protocal=True) for x in urls]

    # 保存实际可使用的网站列表
    utils.write_file(filename=os.path.join(DATA_BASE, "valid-domains.txt"), lines=list(set(domains)))

    # 如有必要，上传至 Gist
    if gist_id and access_token:
        files, push_conf = {}, {"gistid": gist_id, "filename": list(records.keys())[0]}

        for k, v in records.items():
            if os.path.exists(v) and os.path.isfile(v):
                with open(v, "r", encoding="utf8") as f:
                    files[k] = {"content": f.read(), "filename": k}

        if urls:
            files[subscribes_file] = {"content": "\n".join(urls), "filename": subscribes_file}

        if files:
            push_client = push.PushToGist(token=access_token)

            # 上传
            success = push_client.push_to(content="", push_conf=push_conf, payload={"files": files}, group="collect")
            if success:
                logger.info(f"upload proxies and subscriptions to gist successed")
            else:
                logger.error(f"upload proxies and subscriptions to gist failed")

    # 清理工作空间
    workflow.cleanup(workspace, [])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-a",
        "--all",
        dest="all",
        action="store_true",
        default=False,
        help="generate full configuration for clash",
    )

    parser.add_argument(
        "-b",
        "--both",
        dest="both",
        action="store_true",
        default=False,
        help="save results in both clash and mixed formats, only clash is saved by default",
    )

    parser.add_argument(
        "-c",
        "--chuck",
        dest="chuck",
        action="store_true",
        default=False,
        help="discard candidate sites that may require human-authentication",
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
        "-e",
        "--easygoing",
        dest="easygoing",
        action="store_true",
        default=False,
        help="try registering with a gmail alias when you encounter a whitelisted mailbox",
    )

    parser.add_argument(
        "-f",
        "--flow",
        type=int,
        required=False,
        default=0,
        help="remaining traffic available for use, unit: GB",
    )

    parser.add_argument(
        "-g",
        "--gist",
        type=str,
        required=False,
        default=os.environ.get("GIST_LINK", ""),
        help="github username and gist id, separated by '/'",
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
        "-k",
        "--key",
        type=str,
        required=False,
        default=os.environ.get("GIST_PAT", ""),
        help="github personal access token for editing gist",
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
        "-m",
        "--mixed",
        dest="mixed",
        action="store_true",
        default=False,
        help="convert and save as mixed format",
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
        help="overwrite domains",
    )

    parser.add_argument(
        "-p",
        "--pages",
        type=int,
        required=False,
        default=sys.maxsize,
        help="max page number when crawling telegram",
    )

    parser.add_argument(
        "-r",
        "--refresh",
        dest="refresh",
        action="store_true",
        default=False,
        help="refresh and remove expired proxies with existing subscriptions",
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
        "--vitiate",
        type=int,
        required=False,
        default=0,
        help="ignoring default proxies filter rules",
    )

    parser.add_argument(
        "-y",
        "--yourself",
        type=str,
        required=False,
        default=os.environ.get("CUSTOMIZE_LINK", ""),
        help="the url to the list of airports that you maintain yourself",
    )

    aggregate(args=parser.parse_args())
