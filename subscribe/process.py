# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import argparse
import base64
import itertools
import json
import os
import re
import sys
import time
import traceback

import executable
import location
import pipeline
import push
import utils
import workflow
import yaml
from airport import AirPort
from config.models import NodeInput, ProcessConfig, StorageItem
from logger import logger
from workflow import TaskConfig

import clash
import subconverter

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def parse_workflow_mode(raw: str | None = None) -> int:
    text = utils.trim(raw if raw is not None else os.environ.get("WORKFLOW_MODE", "0"))
    return 0 if not text.isdigit() else min(max(int(text), 0), 2)


def load_configs(
    url: str,
    only_check: bool = False,
    num_threads: int = 0,
    display: bool = True,
    retry: int = 3,
    mode: int = 0,
) -> ProcessConfig:
    from crawl.engine import run

    raw = {}
    try:
        if re.match(
            r"^(https?:\/\/(([a-zA-Z0-9]+-?)+[a-zA-Z0-9]+\.)+[a-zA-Z]+)(:\d+)?(\/.*)?(\?.*)?(#.*)?$",
            url,
        ):
            headers = {"User-Agent": utils.USER_AGENT, "Referer": url}
            content = utils.http_get(url=url, headers=headers, retry=max(retry, 1), timeout=120)
            if not content:
                logger.error(f"cannot fetch config from remote, url: {utils.hide(url=url)}")
            else:
                os.environ["SUBSCRIBE_CONF"] = url
                raw = json.loads(content)
        else:
            localfile = os.path.abspath(url)
            if os.path.exists(localfile) and os.path.isfile(localfile):
                raw = json.loads(open(localfile, "r", encoding="utf8").read())
                os.environ["SUBSCRIBE_CONF"] = localfile

        config = ProcessConfig.parse(raw or {})
        pushtool = push.get_instance(config.storage)
        config.verify(pushtool)
        crawl_enabled = bool(config.crawl and config.crawl.enable)
        if not only_check:
            if mode == 1 and not crawl_enabled:
                logger.warning("exit process because mode=1 and crawling task is disabled")
                sys.exit(0)
            if crawl_enabled:
                config.sites.extend(
                    run(config.crawl, storage=config.storage, num_threads=num_threads, display=display, mode=mode)
                )
                if mode == 1:
                    sys.exit(0)
        return config
    except SystemExit as e:
        if e.code != 0:
            logger.error("parse configuration failed due to process abnormally exits")
        sys.exit(e.code)
    except ValueError as e:
        logger.error(f"invalid configuration: {e}")
        sys.exit(0)
    except Exception:
        logger.error(f"occur error when load task config:\n{traceback.format_exc()}")
        sys.exit(0)


def assign(
    pc: ProcessConfig,
    retry: int,
    bin_name: str,
    remain: bool,
    pushtool: push.PushTo,
    only_check: bool = False,
    rigid: bool = True,
    special_protocols: bool | None = None,
) -> tuple[list[TaskConfig], dict[str, list[int]]]:
    if not isinstance(pc, ProcessConfig) or not isinstance(pushtool, push.PushTo):
        return [], {}

    special_protocols = AirPort.enable_special_protocols(special_protocols)

    tasks, groups = pipeline.assign_sites(
        sites=pc.sites,
        groups=pc.groups,
        retry=retry,
        bin_name=bin_name,
        allow_gmail_alias=not rigid,
        special_protocols=special_protocols,
    )

    if (remain or only_check) and pc.groups:
        if only_check:
            tasks, groups, globalid = [], {k: [] for k in pc.groups.keys()}, 0
        else:
            globalid = max([task.taskid for task in tasks], default=0)

        for name, group in pc.groups.items():
            taskids = groups.get(name, [])
            if not group.targets:
                continue
            values = list(group.targets.values())
            item = pc.storage.items.get(values[0])
            subscribe = pushtool.raw_url(item=item) if item else ""
            if name not in groups or not subscribe:
                continue
            globalid += 1
            tasks.append(
                TaskConfig(
                    name=f"remains-{name}",
                    taskid=globalid,
                    nodes=NodeInput(subscribe=subscribe),
                    index=-1,
                    retry=max(1, retry),
                    bin_name=bin_name,
                    special_protocols=special_protocols,
                )
            )
            taskids.append(globalid)
            groups[name] = taskids
    return tasks, groups


def aggregate(args: argparse.Namespace) -> None:
    if not args or not isinstance(args, argparse.Namespace):
        return

    clash_bin, subconverter_bin = executable.which_bin()
    display = not args.invisible
    retry = min(max(1, args.retry), 10)

    # parse config
    server = utils.trim(args.server) or os.environ.get("SUBSCRIBE_CONF", "").strip()
    process_config = load_configs(
        url=server,
        only_check=args.check,
        num_threads=args.num,
        display=display,
        retry=retry,
        mode=args.mode,
    )

    pushtool = push.get_instance(process_config.storage)

    # generate tasks
    tasks, groups = assign(
        pc=process_config,
        retry=retry,
        bin_name=subconverter_bin,
        remain=not args.overwrite,
        pushtool=pushtool,
        only_check=args.check,
        rigid=not args.flexible,
        special_protocols=args.special_protocols,
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
            if tasks[i]:
                for url in tasks[i].nodes.subscribe_list():
                    subscribes[url] = False
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
        filename = "config.yaml"
        starttime = time.time()
        nochecks = pipeline.check_alive_proxies(
            proxies=proxies,
            clash_bin=clash_bin,
            workspace=workspace,
            filename=filename,
            timeout=args.timeout,
            test_url=args.url,
            delay=process_config.delay,
            num_threads=args.num,
            display=display,
            skip=args.skip_alive_check,
            group=k,
        )

        for item in nochecks:
            item.pop("sub", "")

        if len(nochecks) <= 0:
            logger.error(f"cannot fetch any proxy, group=[{k}], cost: {time.time()-starttime:.2f}s")
            continue

        group = process_config.groups.get(k)
        if not group:
            continue
        emoji = group.emoji
        list_only = group.list_only

        if group.regularize and group.regularize.enable:
            nochecks = location.regularize(
                proxies=nochecks,
                num_threads=args.num,
                show_progress=display,
                locate=group.regularize.locate and not args.skip_alive_check,
                residential=group.regularize.residential and not args.skip_alive_check,
                ip_library=group.regularize.library,
                digits=max(1, group.regularize.digits),
                score=group.regularize.score,
            )

        source_file, data = "config.yaml", {"proxies": nochecks}
        filepath = os.path.join(PATH, "subconverter", source_file)
        with open(filepath, "w+", encoding="utf8") as f:
            yaml.add_representer(clash.QuotedStr, clash.quoted_scalar)
            yaml.dump(data, f, allow_unicode=True)

        targets = group.targets
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
                persisted = pushtool.push_to(
                    content=content,
                    item=process_config.storage.items.get(storage_name, StorageItem()),
                    group=f"{k}::{target}",
                )

            # clean workspace
            workflow.cleanup(os.path.join(PATH, "subconverter"), [dest_file, "generate.ini"])

            if content and not persisted:
                filename = os.path.join(PATH, "data", f"{k}-{dest_file}")

                logger.error(f"storage config to remote failed, group: {k}, target: {target}, save it to {filename}")
                utils.write_file(filename=filename, lines=content)

        workflow.cleanup(os.path.join(PATH, "subconverter"), [source_file])
        cost = "{:.2f}s".format(time.time() - starttime)
        logger.info(f"group [{k}] process finished, count: {len(nochecks)}, cost: {cost}")

    workflow.refresh(
        config=process_config,
        push=pushtool,
        alives=dict(subscribes),
        skip_remark=args.skip_remark,
    )


if __name__ == "__main__":
    env_parser = argparse.ArgumentParser(add_help=False)
    env_parser.add_argument(
        "-e",
        "--environment",
        type=str,
        default=".env",
        help="environment file name",
    )
    env_args, _ = env_parser.parse_known_args()
    utils.load_dotenv(env_args.environment)

    parser = argparse.ArgumentParser(parents=[env_parser])
    parser.add_argument(
        "-c",
        "--check",
        dest="check",
        action="store_true",
        default=False,
        help="only check proxies are alive",
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
        "-m",
        "--mode",
        type=int,
        choices=[0, 1, 2],
        default=parse_workflow_mode(),
        help="workflow mode: 0=crawl+aggregate, 1=crawl only, 2=aggregate only",
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
        default=utils.trim(os.environ.get("SUBSCRIBE_CONF", "")),
        help="remote config file",
    )

    parser.add_argument(
        "--skip-alive-check",
        action=argparse.BooleanOptionalAction,
        default=utils.env_bool("SKIP_ALIVE_CHECK", False),
        help="skip proxy liveness check",
    )

    parser.add_argument(
        "--skip-remark",
        action=argparse.BooleanOptionalAction,
        default=utils.env_bool("SKIP_REMARK", False),
        help="skip remark update for crawled subscriptions",
    )

    parser.add_argument(
        "--special-protocols",
        action=argparse.BooleanOptionalAction,
        default=utils.env_bool("ENABLE_SPECIAL_PROTOCOLS", True),
        help="include special protocols such as vless and hysteria",
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
    aggregate(args=args)
