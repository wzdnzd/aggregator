# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import argparse
import datetime
import itertools
import json
import multiprocessing
import os
import platform
import random
import re
import ssl
import string
import subprocess
import sys
import time
import traceback
import urllib
import urllib.parse
import urllib.request
from multiprocessing.managers import ListProxy
from threading import Lock

import yaml

EMAILS_DOMAINS = [
    "@gmail.com",
    "@outlook.com",
    "@163.com",
    "@126.com",
    "@sina.com",
    "@hotmail.com",
    "@qq.com",
    "@foxmail.com",
]

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

FILE_LOCK = Lock()


class TempSite:
    def __init__(self, name: str, site: str, sub: str):
        if site.endswith("/"):
            site = site[: len(site) - 1]

        if sub.strip() != "":
            self.sub = sub
            self.fetch = ""
            self.ref = extract_domain(sub)
            self.registed = True
        else:
            self.sub = f"{site}/api/v1/client/subscribe?token="
            self.fetch = f"{site}/api/v1/user/server/fetch"
            self.registed = False

        self.reg = f"{site}/api/v1/passport/auth/register"
        self.ref = site
        self.name = name
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.114 Safari/537.36 Edg/103.0.1264.62",
            "Referer": self.ref,
        }

    def register(self, email: str, password: str, retry: int = 3) -> tuple[str, str]:
        if retry <= 0:
            return "", ""

        params = {
            "email": email,
            "password": password,
            "invite_code": None,
            "email_code": None,
        }

        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        headers = self.headers
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            request = urllib.request.Request(
                self.reg, data=data, headers=headers, method="POST"
            )
            response = urllib.request.urlopen(request, context=CTX)
            if not response or response.getcode() != 200:
                return "", ""

            token = json.loads(response.read())["data"]["token"]
            cookie = get_cookie(response.getheader("Set-Cookie"))
            subscribe = self.sub + token
            return subscribe, cookie
        except:
            return self.register(email, password, retry - 1)

    def fetch_unused(self, cookie: str, rate: float) -> list:
        if "" == cookie.strip() or "" == self.fetch.strip():
            return []

        self.headers["Cookie"] = cookie
        try:
            proxies = []
            request = urllib.request.Request(self.fetch, headers=self.headers)
            response = urllib.request.urlopen(request, timeout=5, context=CTX)
            if response.getcode() != 200:
                return proxies

            datas = json.loads(response.read())["data"]
            for item in datas:
                if float(item.get("rate", "1.0")) > rate:
                    proxies.append(item.get("name"))

            return proxies
        except:
            return []

    def get_subscribe(self, retry: int) -> tuple[str, str]:
        if self.registed:
            return self.sub, ""

        password = "".join(
            random.sample(
                string.ascii_letters + string.digits + string.ascii_lowercase,
                random.randint(8, 10),
            )
        )
        email = password + random.choice(EMAILS_DOMAINS)
        return self.register(email=email, password=password, retry=retry)

    def parse(
        self,
        url: str,
        cookie: str,
        retry: int,
        rate: float,
        index: int,
        subconverter: str,
        tag: str,
    ) -> list:
        if "" == url:
            return []

        # count = 1
        # while count <= retry:
        #     try:
        #         request = urllib.request.Request(url=url, headers=self.headers)
        #         response = urllib.request.urlopen(request, timeout=10, context=CTX)
        #         v2conf = str(response.read(), encoding="utf8")

        #         # 读取附件内容
        #         disposition = response.getheader("content-disposition", "")
        #         v2conf = ""
        #         if disposition:
        #             print(str(response.read(), encoding="utf8"))
        #             regex = "(filename)=(\S+)"
        #             content = re.findall(regex, disposition)
        #             if content:
        #                 attachment = os.path.join(
        #                     os.path.abspath(os.path.dirname(__file__)),
        #                     content[0][1],
        #                 )
        #                 if os.path.exists(attachment) or os.path.isfile(attachment):
        #                     v2conf = str(
        #                         open(attachment, "r", encoding="utf8").read(),
        #                         encoding="utf8",
        #                     )
        #                     os.remove(attachment)
        #         else:
        #             v2conf = str(response.read(), encoding="utf8")

        #         break
        #     except:
        #         v2conf = ""

        #     count += 1

        v2conf = http_get(url=url, headers=self.headers, retry=retry)
        # if "" == v2conf.strip() or not re.match("^[0-9a-zA-Z=]*$", v2conf):
        if "" == v2conf.strip() or "{" in v2conf:
            return []

        artifact = f"{self.name}{str(index)}"
        v2ray_file = os.path.join(PATH, "subconverter", f"{artifact}.txt")
        clash_file = os.path.join(PATH, "subconverter", f"{artifact}.yaml")

        with open(v2ray_file, "w+") as f:
            f.write(v2conf)
            f.flush()

        generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
        success = subconverter_conf(
            generate_conf, artifact, f"{artifact}.txt", f"{artifact}.yaml", "clash"
        )
        if not success:
            print("cannot generate subconverter config file")
            return []

        time.sleep(2)
        success = convert(binname=subconverter, artifact=artifact)
        os.remove(v2ray_file)
        if not success:
            return []

        with open(clash_file, "r", encoding="utf8") as reader:
            config = yaml.load(reader, Loader=yaml.SafeLoader)
            nodes = config.get("proxies", [])

        # 已经读取，可以删除
        os.remove(clash_file)

        proxies = []
        unused_nodes = self.fetch_unused(cookie, rate)
        for item in nodes:
            if item.get("name") in unused_nodes:
                continue

            item["name"] = re.sub(r"[\^\?\:\/]|\s+", " ", item.get("name")).strip()

            if index >= 0:
                mode = index % 26
                factor = index // 26 + 1
                letter = string.ascii_uppercase[mode]
                item["name"] = "{}-{}".format(item.get("name"), letter * factor)

            # 方便标记已有节点，最多留99天
            if "" != tag:
                if not re.match(f".*-{tag}\d+$", item["name"]):
                    item["name"] = "{}-{}".format(item.get("name"), tag + "01")
                else:
                    words = item["name"].rsplit(f"-{tag}")
                    if not words[1].isdigit():
                        continue
                    num = int(words[1]) + 1
                    if num > 99:
                        continue

                    num = "0" + str(num) if num <= 9 else str(num)
                    name = words[0] + f"-{tag}{num}"
                    item["name"] = name

            proxies.append(item)

        return proxies


def fetch(
    name,
    url: str,
    sub: str,
    index: int,
    retry: int,
    rate: float,
    subconverter: str,
    tag: str,
) -> list:
    obj = TempSite(name, url, sub)

    print(f"start fetch proxy: name=[{name}]\tdomain=[{url}]")
    url, cookie = obj.get_subscribe(retry)
    return obj.parse(url, cookie, retry, rate, index, subconverter, tag.upper())


def cmd(command: list) -> bool:
    if command is None or len(command) == 0:
        return False

    print("command: {}".format(" ".join(command)))

    p = subprocess.Popen(command)
    p.wait()
    return p.returncode == 0


def subconverter_conf(
    filepath: str, name: str, source: str, dest: str, target: str
) -> None:
    if not filepath or not name or not source or not dest or not target:
        print("invalidate arguments, so cannot execute subconverter")
        return False

    try:
        name = f"[{name.strip()}]"
        path = f"path={dest.strip()}"
        url = f"url={source.strip()}"
        target = f"target={target.strip()}"

        lines = [name, path, target, url, "\n"]
        content = "\n".join(lines)

        FILE_LOCK.acquire(30)
        with open(filepath, "a+", encoding="utf8") as f:
            f.write(content)
            f.flush()
        FILE_LOCK.release()

        return True
    except:
        return False


def chmod(binfile: str) -> None:
    if not os.path.exists(binfile) or os.path.isdir(binfile):
        raise ValueError(f"cannot found bin file: {binfile}")

    operating_system = str(platform.platform())
    if operating_system.startswith("Windows"):
        return
    elif operating_system.startswith("macOS") or operating_system.startswith("Linux"):
        cmd(["chmod", "+x", binfile])
    else:
        print("Unsupported Platform")
        sys.exit(0)


def convert(binname: str, artifact: str = "") -> bool:
    binpath = os.path.join(PATH, "subconverter", binname)
    chmod(binpath)
    args = [binpath, "-g"]
    if artifact is not None and "" != artifact:
        args.append("--artifact")
        args.append(artifact)

    return cmd(args)


def get_cookie(text: str) -> str:
    regex = "(_session)=(.+?);"
    if not text:
        return ""

    content = re.findall(regex, text)
    cookie = ";".join(["=".join(x) for x in content]).strip()
    return cookie


def cleanup(process: subprocess.Popen, filepath: str, filenames: list = []) -> None:
    for name in filenames:
        filename = os.path.join(filepath, name)
        if os.path.exists(filename):
            os.remove(filename)

    process.terminate()


def generate_config(path: str, proxies: list, filename: str) -> list:
    os.makedirs(path, exist_ok=True)
    external_config = filter(proxies)
    config = {
        "port": 7890,
        "socks-port": 7891,
        "external-controller": "127.0.0.1:9090",
        "mode": "Rule",
        "log-level": "silent",
    }

    config.update(external_config)
    with open(os.path.join(path, filename), "w+", encoding="utf8") as f:
        yaml.dump(config, f, allow_unicode=True)

    return config.get("proxies", [])


def filter(proxies: list) -> dict:
    ss_supported_ciphers = [
        "aes-128-gcm",
        "aes-192-gcm",
        "aes-256-gcm",
        "aes-128-cfb",
        "aes-192-cfb",
        "aes-256-cfb",
        "aes-128-ctr",
        "aes-192-ctr",
        "aes-256-ctr",
        "rc4-md5",
        "chacha20-ietf",
        "xchacha20",
        "chacha20-ietf-poly1305",
        "xchacha20-ietf-poly1305",
    ]
    ssr_supported_obfs = [
        "plain",
        "http_simple",
        "http_post",
        "random_head",
        "tls1.2_ticket_auth",
        "tls1.2_ticket_fastauth",
    ]
    ssr_supported_protocol = [
        "origin",
        "auth_sha1_v4",
        "auth_aes128_md5",
        "auth_aes128_sha1",
        "auth_chain_a",
        "auth_chain_b",
    ]
    vmess_supported_ciphers = ["auto", "aes-128-gcm", "chacha20-poly1305", "none"]
    config = {
        "proxies": [],
        "proxy-groups": [
            {
                "name": "automatic",
                "type": "url-test",
                "proxies": [],
                "url": "https://www.google.com/favicon.ico",
                "interval": 300,
            },
            {"name": "🌐 Proxy", "type": "select", "proxies": ["automatic"]},
        ],
        "rules": ["MATCH,🌐 Proxy"],
    }

    # 防止多个代理节点名字相同导致clash配置错误
    groups = {}
    for key, group in itertools.groupby(proxies, key=lambda p: p.get("name", "")):
        items = groups.get(key, [])
        items.extend(list(group))
        groups[key] = items

    proxies.clear()
    for _, items in groups.items():
        size = len(items)
        if size <= 1:
            proxies.extend(items)
            continue
        for i in range(size):
            item = items[i]
            mode = i % 26
            factor = i // 26 + 1
            letter = string.ascii_uppercase[mode]
            item["name"] = "{}{}".format(item.get("name"), letter * factor)
            proxies.append(item)

    # 按名字排序方便在节点相同时优先保留名字靠前的
    sorted(proxies, key=lambda p: p.get("name", ""))
    for item in proxies:
        try:
            item["port"] = int(item["port"])
            if item["type"] == "ss":
                if item["cipher"] not in ss_supported_ciphers:
                    continue
            elif item["type"] == "ssr":
                if item["cipher"] not in ss_supported_ciphers:
                    continue
                if item["obfs"] not in ssr_supported_obfs:
                    continue
                if item["protocol"] not in ssr_supported_protocol:
                    continue
            elif item["type"] == "vmess":
                if "udp" in item and item["udp"] not in [False, True]:
                    continue
                if "tls" in item and item["tls"] not in [False, True]:
                    continue
                if "skip-cert-verify" in item and item["skip-cert-verify"] not in [
                    False,
                    True,
                ]:
                    continue
                if item["cipher"] not in vmess_supported_ciphers:
                    continue
            elif item["type"] == "trojan":
                if "udp" in item and item["udp"] not in [False, True]:
                    continue
                if "skip-cert-verify" in item and item["skip-cert-verify"] not in [
                    False,
                    True,
                ]:
                    continue
            elif item["type"] == "snell":
                if "udp" in item and item["udp"] not in [False, True]:
                    continue
                if "skip-cert-verify" in item and item["skip-cert-verify"] not in [
                    False,
                    True,
                ]:
                    continue
            elif item["type"] == "http":
                if "tls" in item and item["tls"] not in [False, True]:
                    continue
            elif item["type"] == "socks5":
                if "tls" in item and item["tls"] not in [False, True]:
                    continue
                if "udp" in item and item["udp"] not in [False, True]:
                    continue
                if "skip-cert-verify" in item and item["skip-cert-verify"] not in [
                    False,
                    True,
                ]:
                    continue
            else:
                continue

            if exists(item, config["proxies"]):
                continue

            config["proxies"].append(item)
            config["proxy-groups"][0]["proxies"].append(item["name"])
            config["proxy-groups"][1]["proxies"].append(item["name"])
        except:
            continue

    return config


def exists(proxy: dict, proxies: list) -> bool:
    if not proxy:
        return True
    if not proxies:
        return False

    protocal = proxy.get("type", "")
    if protocal == "ss" or protocal == "trojan":
        return any(
            p.get("server", "").lower() == proxy.get("server", "").lower()
            and p.get("port", 0) == proxy.get("port", 0)
            and p.get("password", "").lower() == proxy.get("password", "").lower()
            for p in proxies
        )
    elif protocal == "ssr":
        return any(
            p.get("server", "").lower() == proxy.get("server", "").lower()
            and p.get("port", 0) == proxy.get("port", 0)
            and p.get("protocol-param", "").lower()
            == proxy.get("protocol-param", "").lower()
            for p in proxies
        )
    elif protocal == "vmess":
        return any(
            p.get("server", "").lower() == proxy.get("server", "").lower()
            and p.get("port", 0) == proxy.get("port", 0)
            and p.get("uuid", "").lower() == proxy.get("uuid", "").lower()
            for p in proxies
        )
    elif protocal == "snell":
        return any(
            p.get("server", "").lower() == proxy.get("server", "").lower()
            and p.get("port", 0) == proxy.get("port", 0)
            and p.get("psk", "").lower() == proxy.get("psk", "").lower()
            for p in proxies
        )
    elif protocal == "http" or protocal == "socks5":
        return any(
            p.get("server", "").lower() == proxy.get("server", "").lower()
            and p.get("port", 0) == proxy.get("port", 0)
            for p in proxies
        )

    return True


def check(
    alive: ListProxy,
    proxy: dict,
    api_url: str,
    semaphore: multiprocessing.Semaphore,
    timeout: int,
    test_url: str,
) -> None:
    proxy_name = urllib.parse.quote(proxy.get("name", ""))
    base_url = f"{api_url}/proxies/{proxy_name}/delay?timeout={str(timeout)}&url="

    try:
        request = urllib.request.Request(url=base_url + test_url)
        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        data = json.loads(response.read())
        if data.get("delay", -1) <= 0:
            return

        request = urllib.request.Request(
            url=base_url
            + "https://www.youtube.com/s/player/23010b46/player_ias.vflset/en_US/remote.js"
        )
        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        data = json.loads(response.read())
        if data.get("delay", -1) <= 0:
            return

        request = urllib.request.Request(
            url=base_url + "https://cachefly.cachefly.net/10mb.test"
        )
        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        data = json.loads(response.read())
        if data.get("delay", -1) > 0:
            alive.append(proxy)
    except:
        pass

    semaphore.release()


def push(filepath: str, push_conf: dict, group: str, retry: int = 5) -> bool:
    folderid = push_conf.get("folderid", "")
    fileid = push_conf.get("fileid", "")
    key = push_conf.get("key", "")

    if (
        not os.path.exists(filepath)
        or not os.path.isfile(filepath)
        or "" == key.strip()
        or "" == fileid.strip()
    ):
        return False

    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    content = open(filepath, "r", encoding="utf8").read()
    data = json.dumps({"content": {"format": "text", "value": content}}).encode("UTF8")
    url = f"https://api.paste.gg/v1/pastes/{folderid}/files/{fileid}"

    try:
        request = urllib.request.Request(
            url, data=data, headers=headers, method="PATCH"
        )
        response = urllib.request.urlopen(request, context=CTX)
        if response.getcode() == 204:
            print(
                f"[PushSuccess] push subscribes information to remote successed, group=[{group}]"
            )
            return True
        else:
            print(
                "[PushError]: group=[{}], error message: \n{}".format(
                    group, response.read().decode("unicode_escape")
                )
            )
            return False

    except Exception:
        print(f"[PushError]: group=[{group}], error message:")
        traceback.print_exc()

        retry -= 1
        if retry > 0:
            return push(filepath, push_conf, group, retry)

        return False


def load_configs(file: str, url: str) -> tuple[list, dict]:
    def parse_config(config: dict) -> None:
        sites.extend(config.get("domains", []))
        push_configs.update(config.get("push", {}))

        telegram = config.get("telegram", {})
        disable = telegram.get("disable", False)
        push_to = list(set(telegram.get("push_to", [])))
        items = list(set([str(item).strip() for item in telegram.get("users", [])]))
        if not disable and items and push_to:
            for item in items:
                ps = users.get(item, [])
                ps.extend(push_to)
                users[item] = list(set(ps))

    sites, users, push_configs = [], {}, {}
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

            content = http_get(url=url, headers=headers)
            if not content:
                print(f"cannot fetch config from remote, url: {url}")
            else:
                parse_config(json.loads(content))

        # 从telegram抓取订阅信息
        if users:
            result = batch_crawl(users, 7)
            sites.extend(result)
    except:
        print("occur error when load task config")

    return sites, push_configs


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


def validate_push(push_configs: dict) -> dict:
    configs = {}
    for k, v in push_configs.items():
        if (
            v.get("folderid", "")
            and v.get("fileid", "")
            and v.get("key", "")
            and v.get("username", "")
        ):
            configs[k] = v

    return configs


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
                tasks.append([name, url, sub, -1, retry, rate, subconverter, tag])
            else:
                subtasks = [
                    [name, url, sub, i, retry, rate, subconverter, tag]
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
            tasks.append(["remains", "", sub, -1, retry, rate, subconverter, "R"])
            jobs[k] = tasks
    return jobs


def execute_names() -> tuple[str, str]:
    operating_system = str(platform.platform())
    if operating_system.startswith("macOS"):
        if "arm64" in operating_system:
            clashname = "clash-darwin-arm"
        else:
            clashname = "clash-darwin-arm"

        subconverter = "subconverter-mac"
    elif operating_system.startswith("Linux"):
        clashname = "clash-linux"
        subconverter = "subconverter-linux"
    elif operating_system.startswith("Windows"):
        clashname = "clash-windows.exe"
        subconverter = "subconverter-windows.exe"
    else:
        print("Unsupported Platform")
        sys.exit(1)

    return clashname, subconverter


def extract_domain(url: str) -> str:
    if not url:
        return ""

    start = url.find("//")
    if start == -1:
        start = -2

    end = url.find("/", start + 2)
    if end == -1:
        end = len(url) - 1

    return url[start + 2 : end]


def batch_crawl(conf: dict, period: int, thread: int = 50) -> list:
    if not conf:
        return []

    params = [[k, period, v] for k, v in conf.items()]
    cpu_count = multiprocessing.cpu_count()
    num = len(params) if len(params) <= cpu_count else cpu_count

    pool = multiprocessing.Pool(num)
    results = pool.starmap(crawl_telegram, params)
    pool.close()

    tasks = {}
    for r in results:
        for k, v in r.items():
            items = tasks.get(k, [])
            items.extend(v)
            tasks[k] = list(set(items))

    if not tasks:
        print("cannot any subscribe url from telegram")
        return []

    with multiprocessing.Manager() as manager:
        availables = manager.list()
        processes = []
        semaphore = multiprocessing.Semaphore(max(thread, 1))
        time.sleep(random.randint(1, 3))
        for k, v in tasks.items():
            semaphore.acquire()
            p = multiprocessing.Process(
                target=validate_available, args=(k, v, availables, semaphore)
            )
            p.start()
            processes.append(p)
        for p in processes:
            p.join()

        time.sleep(random.randint(1, 3))
        return list(availables)


def crawl_telegram(
    userid: str, period: int, push_to: list = [], limits: int = 20
) -> dict:
    if not userid:
        return {}

    now = time.time() - 3600 * 12
    crawl_time = datetime.datetime.fromtimestamp(now).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"https://telemetr.io/post-list-ajax/{userid}/with-date-panel?period={period}&date={crawl_time}"

    content = http_get(url=url)
    if content == "":
        return {}

    regex = "https://\S+/api/v1/client/subscribe\?token=[a-zA-Z0-9]+|https://\S+/link/[a-zA-Z0-9]+\?sub=\d"
    subscribes = re.findall(regex, content)

    collections = {}
    for s in subscribes:
        if "token=" in s:
            s += "&flag=v2ray"
        collections[s] = push_to
        if len(collections) >= limits:
            break

    return collections


def http_get(url: str, headers: dict = None, retry: int = 3) -> str:
    if not re.match(
        "^(https?:\/\/(\S+\.)+[a-zA-Z]+)(:\d+)?(\/.*)?(\?.*)?(#.*)?$",
        url,
    ):
        print(f"invalid url: {url}")
        return ""

    if retry <= 0:
        print(f"achieves max retry, url={url}")
        return ""

    if not headers:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.114 Safari/537.36 Edg/103.0.1264.62",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        }

    try:
        request = urllib.request.Request(url=url, headers=headers)
        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        status_code = response.getcode()
        content = str(response.read(), encoding="utf8")
        if status_code != 200:
            print(f"request failed, status code: {status_code}\t message: {content}")
            return ""

        return content
    except urllib.error.HTTPError as e:
        print(f"request failed, url=[{url}], code: {e.code}")
        if e.code == 503:
            return http_get(url, headers, retry - 1)
        return ""
    except urllib.error.URLError as e:
        print(f"request failed, url=[{url}], message: {e.reason}")
        return ""
    except Exception:
        return http_get(url, headers, retry - 1)


def validate_available(
    url: str, push_to: list, availables: ListProxy, semaphore: multiprocessing.Semaphore
) -> None:
    if http_get(url=url, retry=2) != "":
        item = {"name": naming_task(url), "sub": url, "push_to": push_to}
        availables.append(item)

    semaphore.release()


def naming_task(url):
    prefix = extract_domain(url=url).replace(".", "")
    return prefix + "".join(
        random.sample(string.digits + string.ascii_lowercase, random.randint(3, 5))
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
    clash, subconverter = execute_names()

    sites, push_configs = load_configs(file=args.file, url=args.server)
    push_configs = validate_push(push_configs)
    tasks = assign(sites, 5, subconverter, args.remain, push_configs)
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
        results = pool.starmap(fetch, v)
        pool.close()

        proxies = list(itertools.chain.from_iterable(results))
        if len(proxies) == 0:
            print(f"exit because cannot fetch any proxy node, group=[{k}]")
            continue

        workspace = os.path.join(PATH, "clash")
        binpath = os.path.join(workspace, clash)
        filename = "config.yaml"
        proxies = generate_config(workspace, proxies, filename)
        api_url = "http://127.0.0.1:9090"

        chmod(binpath)
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
                    target=check,
                    args=(alive, proxy, api_url, semaphore, args.timeout, args.url),
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

            success = subconverter_conf(
                generate_conf, artifact, source_file, dest_file, "mixed"
            )
            if not success:
                print(f"cannot generate subconverter config file, group=[{k}]")
                continue

            if convert(binname=subconverter, artifact=artifact):
                # 推送到https://paste.gg
                filepath = os.path.join(PATH, "subconverter", dest_file)
                push(filepath, push_configs.get(k, {}), k)

            # 关闭clash
            cleanup(
                process,
                os.path.join(PATH, "subconverter"),
                [source_file, dest_file, "generate.ini"],
            )
