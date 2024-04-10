import argparse
import itertools
import os
import re
import sys

import executable
import utils
import workflow
import yaml
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

    # remove unused key
    nodes = []
    for p in proxies:
        if not isinstance(p, dict):
            continue

        for k in ["sub", "chatgpt", "liveness"]:
            p.pop(k, None)

        nodes.append(p)

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
        default="proxies.yaml",
        help="file path to save merged proxies",
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
