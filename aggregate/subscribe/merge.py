import argparse
import itertools
import os
import random
import re
import subprocess
import sys
import time

import yaml

import clash
import executable
import utils
import workflow
from logger import logger
from workflow import TaskConfig

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def main(args: argparse.Namespace) -> None:
    url = utils.trim(text=args.url)
    if not url:
        logger.error("please provide the url for the subscriptions")
        return

    filename = utils.trim(args.filename)
    if not filename:
        logger.error(f"must specify the file path where the results will be saved")
        return

    content = utils.http_get(url=url, timeout=30)
    groups = re.findall(r"^https?:\/\/[^\s]+", content, flags=re.M)
    if not groups:
        logger.warning("cannot found any valid subscription")
        return

    _, subconverter_bin = executable.which_bin()
    tasks, subscriptions = [], set(groups)
    for sub in subscriptions:
        conf = TaskConfig(name=utils.random_chars(length=8), sub=sub, bin_name=subconverter_bin)
        tasks.append(conf)

    logger.info(f"start generate subscribes information, tasks: {len(tasks)}")
    generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
    if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
        os.remove(generate_conf)

    results = utils.multi_thread_run(func=workflow.execute, tasks=tasks, num_threads=args.num)
    proxies = list(itertools.chain.from_iterable(results))

    if len(proxies) == 0:
        logger.error("exit because cannot fetch any proxy node")
        sys.exit(0)

    filepath = os.path.abspath(filename)
    directory = os.path.dirname(filepath)
    os.makedirs(directory, exist_ok=True)

    nodes, workspace = [], os.path.join(PATH, "clash")
    clash_bin, subconverter_bin = executable.which_bin()
    display = not args.invisible

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

    data = {"proxies": nodes}
    with open(filepath, "w+", encoding="utf8") as f:
        yaml.dump(data, f, allow_unicode=True)
        logger.info(f"found {len(nodes)} proxies, save it to {filepath}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-f",
        "--filename",
        type=str,
        required=False,
        default="self_proxies.yaml",
        help="file path to save merged proxies",
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
        "-s",
        "--skip",
        dest="skip",
        action="store_true",
        default=False,
        help="skip usability checks",
    )

    parser.add_argument(
        "-n",
        "--num",
        type=int,
        required=False,
        default=64,
        help="threads num for concurrent fetch proxy",
    )

    parser.add_argument(
        "-u",
        "--url",
        type=str,
        required=False,
        default=os.environ.get("EXISTS_LINK", ""),
        help="subscriptions link",
    )

    main(args=parser.parse_args())
