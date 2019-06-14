#!/usr/bin/env python
# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2018-04-25

import logging
import multiprocessing
import os
import random
import re
import sys
import time
import warnings
import simplejson as json
from simplejson.decoder import JSONDecodeError

import requests
from requests.exceptions import RequestException

warnings.filterwarnings('ignore')

HEADER = {
    "user-agent":
    "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3803.0 Mobile Safari/537.36",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "zh-CN,zh;q=0.9",
    "dnt": "1",
    "Connection": "keep-alive",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "x-requested-with": "XMLHttpRequest"
}

PROXY = {
    "http": "http:/127.0.0.1:1080",
    "https": "http://127.0.0.1:1080"
}

RETRY_NUM = 5

try:
    import brotli
    HEADER["accept-encoding"] = "gzip, deflate, br"
except ImportError as e:
    HEADER["accept-encoding"] = "gzip, deflate"

PATH = os.path.abspath(os.path.dirname(__file__))

logging.basicConfig(
    filename=os.path.join(PATH, 'checkin.log'),
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

# if python's version is 2, disable requests output info level log
if sys.version_info.major == 2:
    logging.getLogger("requests").setLevel(logging.WARNING)


def config_load(filename):
    if not os.path.exists(filename) or os.path.isdir(filename):
        return

    config = open(filename, 'r').read()
    return json.loads(config)


def get_randint(min_num, max_num):
    if min_num > max_num:
        raise ValueError("Illegal arguments...")
    return random.randint(min_num, max_num)


def extract_domain(url):
    if not url:
        return ""

    start = url.find("//")
    if start == -1:
        start = -2

    end = url.find("/", start + 2)
    if end == -1:
        end = len(url) - 1

    return url[start + 2:end]


def login(url, params, headers, retry, proxy=False):
    try:
        if proxy:
            response = requests.post(
                url, data=params, headers=headers, allow_redirects=True, proxies=PROXY, verify=False)
        else:
            response = requests.post(
                url, data=params, headers=headers, allow_redirects=True)

        if response.status_code == 200:
            return response.headers

    except RequestException as e:
        logging.error(str(e))
        retry -= 1

        if retry > 0:
            time.sleep(get_randint(30 * 60, 90 * 60))
            login(url, params, headers, retry, proxy)

        logging.error(u"登录失败 URL: {}".format(extract_domain(url)))
        return None


def checkin(url, headers, retry, proxy=False):
    try:
        response = requests.post(
            url, headers=headers, proxies=PROXY, verify=False) if proxy else requests.post(url, headers=headers)

        if response.status_code == 200:
            key = 'Content-Encoding'
            try:
                data = json.loads(brotli.decompress(response.content).decode('utf-8')) \
                    if key in response.headers and response.headers['Content-Encoding'] == 'br' \
                    else response.json()

                logging.info(u"签到成功 URL: {} {}".format(
                    extract_domain(url), data['msg']))
            except JSONDecodeError:
                logging.error(u"签到失败 URL: {}".format(extract_domain(url)))

            return

    except RequestException as e:
        logging.error(str(e))
        retry -= 1

        if retry > 0:
            time.sleep(get_randint(30, 60 * 60))
            checkin(url, headers, retry, proxy)

        logging.error(u"签到失败 URL: {}".format(extract_domain(url)))


def logout(url, headers):
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return 0
        else:
            logging.info(u"退出失败 URL: {}".format(extract_domain(url)))
            return -3
    except RequestException:
        return -3


def get_cookie(headers):
    regex = "(__cfduid|uid|email|key|ip|expire_in)=(.+?);"
    if "set-cookie" not in headers:
        return ''

    content = re.findall(regex, headers["set-cookie"])
    cookie = ';'.join(['='.join(x) for x in content]).strip()

    return cookie


def flow(domain, params, headers, proxy=False):
    domain = domain.strip()
    regex = "(?i)^(https?:\\/\\/)?(www.)?([^\\/]+\\.[^.]*$)"
    flag = re.search(regex, domain)

    if not flag:
        return False

    login_url = domain + "/auth/login"
    checkin_url = domain + "/user/checkin"
    logout_url = domain + "/user/logout"

    headers["origin"] = domain
    headers["referer"] = login_url

    response_header = login(login_url, params, headers, RETRY_NUM, proxy)
    if not response_header:
        return False

    cookie = get_cookie(response_header)
    if len(cookie) <= 0:
        return False

    headers["referer"] = domain + "/user"
    headers["cookie"] = cookie

    checkin(checkin_url, headers, RETRY_NUM, proxy)

    headers[
        "accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8"
    headers["upgrade-insecure-requests"] = "1"

    logout(logout_url, headers)


def wrapper(args):
    flow(args["domain"], args["param"], HEADER, args["proxy"])


def main():
    config = config_load(os.path.join(PATH, 'config.json'))
    if config is None or "domains" not in config or len(config["domains"]) == 0:
        sys.exit(0)

    if "retry" in config and config["retry"] > 0:
        RETRY_NUM = int(config["retry"])

    # only support http(s) proxy
    if "proxyServer" in config and type(config["proxyServer"]) == dict:
        PROXY = config["proxyServer"]

    # sleep
    if "waitTime" in config and 0 < config["waitTime"] <= 24:
        time.sleep(get_randint(0, config["waitTime"] * 60 * 60))

    params = config["domains"]

    cpu_count = multiprocessing.cpu_count()
    num = len(params) if len(params) <= cpu_count else cpu_count

    pool = multiprocessing.Pool(num)
    pool.map(wrapper, params)
    pool.close()


if __name__ == '__main__':
    main()
