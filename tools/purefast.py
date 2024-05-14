# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-12-07

import concurrent.futures
import gzip
import json
import logging
import multiprocessing
import os
import random
import re
import sys
import time
import urllib
import urllib.parse
import urllib.request
import warnings
from base64 import b64decode
from http.client import HTTPResponse
from typing import Any
from urllib.error import HTTPError
from urllib.request import OpenerDirector

warnings.filterwarnings("ignore")
from http import cookiejar

PATH = os.path.abspath(os.path.dirname(__file__))

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36 Edg/108.0.1462.46"

logging.basicConfig(
    filename=os.path.join(PATH, "checkin.log"),
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

# if python's version is 2, disable requests output info level log
if sys.version_info.major == 2:
    logging.getlogging("requests").setLevel(logging.WARNING)


def login(
    url: str,
    opener: OpenerDirector,
    cookies: cookiejar.CookieJar,
    params: dict,
    headers: dict,
    endtime: int,
    retry: int = 3,
) -> tuple[bool, dict]:
    if isblank(url) or not params or retry <= 0 or checkconn(opener, cookies):
        logging.error(f"[PFVPNLoginError] cannot login, url: {url}, retry: {retry}")
        return False, {}

    if not headers:
        headers = {
            "user-agent": USER_AGENT,
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "accept-encoding": "gzip, deflate",
            "referer": url,
            "x-requested-with": "XMLHttpRequest",
        }

    try:
        successed, skip, count = False, False, 25
        while not successed and count > 0 and time.time() < endtime:
            count -= 1
            data = urllib.parse.urlencode(params).encode(encoding="UTF8")
            request = urllib.request.Request(url, data=data, headers=headers, method="POST")
            response = opener.open(request, timeout=10)
            cookie = response.getheader("Set-Cookie")

            if response.getcode() == 200:
                if not skip and not isblank(specified_cookie(cookie, "ge_ua_p", False)):
                    skip, headers = bypass(
                        url=url,
                        opener=opener,
                        cookies=cookies,
                        endtime=endtime,
                        content=read(response),
                        headers=headers,
                        retry=3,
                        starttime=time.time(),
                    )
                    continue

                cookie = get_cookie(cookie)
                successed = not isblank(cookie)
                if successed:
                    cookie = add_or_replace(headers.get("cookie", ""), cookie)
                    headers["cookie"] = cookie
                    break

            time.sleep(random.randint(5, 15) / 10)
        return successed, headers
    except:
        return login(url, opener, cookies, params, headers, endtime, retry - 1)


def checkin(
    url: str,
    opener: OpenerDirector,
    cookies: cookiejar.CookieJar,
    headers: dict,
    endtime: int,
    retry: int = 3,
) -> bool:
    if isblank(url) or not headers or retry <= 0 or checkconn(opener, cookies):
        logging.error(f"[PFVPNError] cannot checkin, url: {url}, retry: {retry}")
        return False
    try:
        successed, skip, count = False, False, 25
        while not skip and not successed and count > 0 and time.time() < endtime:
            count -= 1
            request = urllib.request.Request(url, headers=headers, method="POST")
            response = opener.open(request, timeout=10)

            if response.getcode() == 200:
                if not isblank(specified_cookie(response.getheader("Set-Cookie"), "ge_ua_p", False)):
                    skip, headers = bypass(
                        url=url,
                        opener=opener,
                        cookies=cookies,
                        endtime=endtime,
                        content=read(response),
                        headers=headers,
                        retry=3,
                        starttime=time.time(),
                    )
                    continue

                content = read(response)
                try:
                    data = json.loads(content)
                    successed = data.get("ret", 0) == 1
                    if successed:
                        message = data.get("msg", "")
                        logging.info(f"[PFVPN] checkin successed, message: {message}")
                        break
                except:
                    logging.error(f"[PFVPNError] checkin failed, message: {content}")

            time.sleep(random.randint(5, 15) / 10)
        return successed
    except HTTPError as e:
        if e.status == 307:
            cookie = specified_cookie(e.headers["Set-Cookie"], "WAF_VALIDATOR_ID", True)
            headers["cookie"] = add_or_replace(source=headers.get("cookie", ""), dest=cookie)
            headers["x-cache"] = "BYPASS"
        return checkin(url, opener, cookies, headers, endtime, retry - 1)
    except:
        return checkin(url, opener, cookies, headers, endtime, retry - 1)


def get_cookie(text: str) -> str:
    regex = "(__cfduid|uid|email|key|ip|expire_in)=(.+?);"
    if isblank(text):
        return ""

    content = re.findall(regex, text)
    cookie = ";".join(["=".join(x) for x in content]).strip()

    return cookie


def run(domain: str, params: dict, timeout: int) -> bool:
    domain = extract_domain(url=domain, include_protocal=True)
    if not domain:
        logging.error(f"[PFVPNError] cannot checkin because domain: {domain} is invalidate")
        return False

    login_url = domain + params.get("login", "/auth/login")
    checkin_url = domain + params.get("checkin", "/user/checkin")

    email = params.get("username", "").strip()
    username = email.split("@", maxsplit=1)[0]
    passwd = params.get("password", "").strip()
    try:
        if isblank(email) or isblank(passwd):
            logging.error(f"[PFVPNError] skip checkin for username=[{username}]")
            return False

        passwd = b64decode(passwd)
    except:
        logging.error(f"[PFVPNError] username=[{username}], password error, please encoding it with base64")
        return False

    user_info = {"email": email, "passwd": passwd, "code": ""}
    opener, cookies = build_opener()
    starttime, endtime = time.time(), time.time() + max(timeout, 5)

    successed, headers = login(login_url, opener, cookies, user_info, None, endtime, 3)
    if not successed:
        logging.error(f"[PFVPNError] login failed, skip checkin, username: {username}")
        return successed

    headers["referer"] = domain + "/user"
    headers["content-type"] = "application/json"
    successed = checkin(checkin_url, opener, cookies, headers, endtime, 5)

    cost = round(time.time() - starttime, 2)
    logging.info(f"[PFVPNInfo] finished checkin, username: {username}, result: {successed}, cost: {cost}s")

    return successed


def calsum(cpk: str, nonce: int) -> int:
    if isblank(cpk):
        return -1

    num = 0
    for i in range(len(cpk)):
        c = cpk[i]
        if c.isalnum():
            num += ord(c) * (nonce + i)
    return num


def aboartable_run(domain: str, params: dict, timeout: int = 180) -> None:
    timeout = max(timeout, 0)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        try:
            future = executor.submit(run, domain, params, timeout)
            future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            username = params.get("username", "").split("@", maxsplit=1)[0]
            logging.error(f"[PFVPNError] checkin task aborting due to timeout {timeout}s, username: {username}")
            executor.shutdown(wait=False, cancel_futures=True)


def bypass(
    url: str,
    opener: OpenerDirector,
    cookies: cookiejar.CookieJar,
    endtime: int,
    content: str = "",
    headers: dict = None,
    retry: int = 3,
    starttime: int = -1,
) -> tuple[bool, dict]:
    if isblank(url) or retry <= 0 or checkconn(opener=opener, cookies=cookies):
        return False, headers

    if not headers:
        headers = {
            "user-agent": USER_AGENT,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "accept-language": "zh-CN,zh;q=0.9",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "accept-encoding": "gzip, deflate",
            "referer": url,
            "x-requested-with": "XMLHttpRequest",
        }

    try:
        if isblank(content):
            request = urllib.request.Request(url, headers=headers)
            response = opener.open(request, timeout=10)
            starttime = time.time()
            if response.getcode() >= 400:
                return False, headers
            content = read(response)

        groups = re.findall(r'var\s+cpk(?:\s+)?=(?:\s+)?"(.*)"', content, re.I)
        cpkname = groups[0] if groups else "ge_ua_p"

        groups = re.findall(r'var\s+step(?:\s+)?=(?:\s+)?"(.*)"', content, re.I)
        step = groups[0] if groups else "prev"

        groups = re.findall(r"var\s+nonce(?:\s+)?=(?:\s+)?(\d+);", content, re.I)
        nonce = int(groups[0]) if groups else -1

        cpkvalue = specified_cookie(cookies, cpkname, False)
        if isblank(cpkvalue) or isblank(step) or nonce < 0:
            return False, headers

        time.sleep(max(5 - (time.time() - starttime), 0))
        sumval = calsum(cpk=cpkvalue, nonce=nonce)
        data = urllib.parse.urlencode({"sum": sumval, "nonce": nonce}).encode(encoding="UTF8")
        headers["x-ge-ua-step"] = step
        headers["cookie"] = add_or_replace(source=headers.get("cookie", ""), dest=f"{cpkname}={cpkvalue}")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        successed, count = False, 20
        while not successed and count > 0 and time.time() < endtime:
            count -= 1

            response = opener.open(request, timeout=10)
            if response.getcode() == 200:
                text = read(response)
                if not isblank(text):
                    successed = json.loads(text).get("ok", False)
                    if successed:
                        break

            time.sleep(random.randint(3, 8) / 10)

        headers.pop("x-ge-ua-step", "")
        # remove ge_ua_p from cookie
        cookie = add_or_replace(source=headers.get("cookie", ""), dest=f"{cpkname}=")
        headers["cookie"] = cookie

        if successed:
            # add or replace ge_ua_key and lang
            guk = specified_cookie(response.getheader("Set-Cookie"), "ge_ua_key", concat=True)
            cookie = add_or_replace(source=cookie, dest=f"{guk}; lang=zh-cn")
            headers["cookie"] = cookie
        return successed, headers
    except:
        return bypass(
            url=url,
            opener=opener,
            cookies=cookies,
            endtime=endtime,
            content=content,
            headers=headers,
            retry=retry - 1,
            starttime=starttime,
        )


def specified_cookie(items: Any, key: str, concat: bool = False) -> str:
    value = ""

    if not items or isblank(key):
        return value

    if type(items) == cookiejar.CookieJar:
        for cookie in items:
            if key == cookie.name:
                value = cookie.value
                break

    elif type(items) == str:
        for cookie in items.split(";"):
            words = cookie.split("=", maxsplit=1)
            if len(words) != 2:
                continue
            if key == words[0]:
                value = words[1]
                break

    return f"{key}={value}" if concat and not isblank(value) else value


def add_or_replace(source: str, dest: str) -> str:
    def covertto(content: str) -> dict:
        targets = {}
        if isblank(content):
            return targets

        for text in content.split(";"):
            text = text.strip()
            words = text.split("=", maxsplit=1)
            if len(words) != 2 or isblank(words[0]):
                continue
            targets[words[0]] = words[1]

        return targets

    if isblank(dest):
        return source

    raws, others = covertto(source), covertto(dest)
    raws.update(others)
    items = [f"{k}={v}" for k, v in raws.items() if not isblank(v)]
    return "; ".join(items)


def read(response: HTTPResponse) -> str:
    if not response or type(response) != HTTPResponse:
        return ""
    try:
        content = response.read()
        try:
            content = gzip.decompress(content).decode("utf8")
        except:
            content = str(content, encoding="utf8")
        return content
    except:
        return ""


def loadconf(filename: str = "") -> dict:
    domain = os.environ.get("PFVPN_DOMAIN", "https://purefast.net")
    ustr = os.environ.get("PFVPN_USERNAMES", "")
    pstr = os.environ.get("PFVPN_PASSWORDS", "")

    configs = {}
    try:
        if isblank(domain) or isblank(ustr) or isblank(pstr):
            if not isblank(filename) and os.path.exists(filename) and os.path.isfile(filename):
                configs = json.loads(open(filename, "r").read())
        else:
            configs["domain"] = domain
            usernames, passwords = ustr.split(";"), pstr.split(";")
            if len(usernames) != len(passwords):
                logging.warning(f"[PFVPNError] the number of usernames and the number of passwords do not match")
            else:
                accounts = []
                for i in range(len(usernames)):
                    accounts.append(
                        {
                            "username": usernames[i].strip(),
                            "password": passwords[i].strip(),
                        }
                    )
                configs["accounts"] = accounts
    except:
        logging.error(f"[PFVPNError] loading config error, filename: {filename}")

    return configs


def isblank(text: str) -> bool:
    return not text or type(text) != str or not text.strip()


def build_opener() -> tuple[OpenerDirector, cookiejar.CookieJar]:
    cookies = cookiejar.CookieJar()
    cookie_handle = urllib.request.HTTPCookieProcessor(cookies)
    http_handle = urllib.request.HTTPHandler()
    https_handle = urllib.request.HTTPSHandler()
    opener = urllib.request.build_opener(http_handle, https_handle, cookie_handle)

    return opener, cookies


def checkconn(opener: OpenerDirector, cookies: cookiejar.CookieJar) -> bool:
    return opener is None or type(opener) != OpenerDirector or cookies is None or type(cookies) != cookiejar.CookieJar


def extract_domain(url: str, include_protocal: bool = False) -> str:
    if not url:
        return ""

    start = url.find("//")
    if start == -1:
        start = -2

    end = url.find("/", start + 2)
    if end == -1:
        end = len(url)

    if include_protocal:
        return url[:end]

    return url[start + 2 : end]


def main() -> None:
    config = loadconf(os.path.join(PATH, "purefast.json"))
    domain = config.get("domain", "https://purefast.net")
    accounts = config.get("accounts", [])

    if isblank(domain) or not accounts:
        logging.error(f"[PFVPNError] skip checkin because cannot found any valid config, exit")
        sys.exit(1)

    params = [[domain, x, 300] for x in accounts if x]
    cpu_count = multiprocessing.cpu_count()
    num = len(params) if len(params) <= cpu_count else cpu_count

    pool = multiprocessing.Pool(num)
    pool.starmap(aboartable_run, params)
    pool.close()


if __name__ == "__main__":
    main()
