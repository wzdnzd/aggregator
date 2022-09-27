# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-04-05

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib
import urllib.parse
import urllib.request
import warnings
from random import randint

warnings.filterwarnings("ignore")

HEADER = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36 Edg/100.0.1185.39",
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9",
    "content-language": "zh-CN",
    "content-type": "application/x-www-form-urlencoded",
}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

PATH = os.path.abspath(os.path.dirname(__file__))


def extract_domain(url) -> str:
    if not url:
        return ""

    start = url.find("//")
    if start == -1:
        start = -2

    end = url.find("/", start + 2)
    if end == -1:
        end = len(url) - 1

    return url[start + 2 : end]


def login(url, params, headers, retry) -> str:
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        if response.getcode() == 200:
            return response.getheader("Set-Cookie")
        else:
            print(response.read().decode("UTF8"))
            return ""

    except Exception as e:
        print(str(e))
        retry -= 1

        if retry > 0:
            return login(url, params, headers, retry)

        print("[LoginError] URL: {}".format(extract_domain(url)))
        return ""


def order(url, params, headers, retry) -> str:
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        trade_no = ""
        if response.getcode() == 200:
            result = json.loads(response.read().decode("UTF8"))
            trade_no = result.get("data", "")
        else:
            print(response.read().decode("UTF8"))

        return trade_no

    except Exception as e:
        print(str(e))
        retry -= 1

        if retry > 0:
            return order(url, params, headers, retry)

        print("[OrderError] URL: {}".format(extract_domain(url)))
        return ""


def fetch(url, headers, retry) -> str:
    try:
        request = urllib.request.Request(url, headers=headers, method="GET")
        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        if response.getcode() != 200:
            print(response.read().decode("UTF8"))
            return ""

        data = json.loads(response.read().decode("UTF8"))
        # trade_nos = [x["trade_no"] for x in data if x["type"] == 2]
        for item in data["data"]:
            if item["status"] == 0:
                return item["trade_no"]

        return ""

    except Exception as e:
        print(str(e))
        retry -= 1

        if retry > 0:
            return fetch(url, headers, retry)

        print("[FetchError] URL: {}".format(extract_domain(url)))
        return ""


def payment(url, params, headers, retry) -> bool:
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        success = False
        if response.getcode() == 200:
            result = json.loads(response.read().decode("UTF8"))
            success = result.get("data", False)
        else:
            print(response.read().decode("UTF8"))

        return success

    except Exception as e:
        print(str(e))
        retry -= 1

        if retry > 0:
            return payment(url, params, headers, retry)

        print("[PaymentError] URL: {}".format(extract_domain(url)))
        return False


def check(url, params, headers, retry) -> bool:
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        success = False
        if response.getcode() == 200:
            result = json.loads(response.read().decode("UTF8"))
            success = False if result.get("data", None) is None else True
        else:
            print(response.read().decode("UTF8"))

        return success

    except Exception as e:
        print(str(e))
        retry -= 1

        if retry > 0:
            return check(url, params, headers, retry)

        print("[CheckError] URL: {}".format(extract_domain(url)))
        return False


def get_cookie(text) -> str:
    regex = "((?:v2board)?_session)=((?:.+?);|.*)"
    if not text:
        return ""

    content = re.findall(regex, text)
    cookie = ";".join(["=".join(x) for x in content]).strip()

    return cookie


def config_load(filename) -> dict:
    if not os.path.exists(filename) or os.path.isdir(filename):
        return None

    config = open(filename, "r").read()
    return json.loads(config)


def flow(domain, params, headers, reset, retry) -> bool:
    domain = domain.strip()
    regex = "(?i)^(https?:\\/\\/)?(www.)?([^\\/]+\\.[^.]*$)"
    if not re.search(regex, domain):
        return False

    login_url = domain + params.get("login", "/api/v1/passport/auth/login")
    fetch_url = domain + params.get("fetch", "/api/v1/user/order/fetch")
    order_url = domain + params.get("order", "/api/v1/user/order/save")
    payment_url = domain + params.get("payment", "/api/v1/user/order/checkout")
    method = params.get("method", "0")
    coupon = params.get("couponCode", "")

    headers["origin"] = domain
    headers["referer"] = domain + "/"

    user_info = {
        "email": params.get("email", ""),
        "password": params.get("passwd", ""),
    }

    text = login(login_url, user_info, headers, retry)
    if not text:
        return False

    cookie = get_cookie(text)
    if len(cookie) <= 0:
        return False

    headers["cookie"] = cookie

    trade_no = fetch(fetch_url, headers, retry)

    if trade_no:
        payload = {"trade_no": trade_no, "method": method}
        if coupon:
            payload["coupon_code"] = coupon
        if not payment(payment_url, payload, headers, retry):
            return False

    period = "resetPeriod" if reset else "renewalPeriod"
    if not params.get(period):
        if reset:
            params[period] = "reset_price"
        else:
            print("not support renewal")
            return False

    plan_id = params.get("planId", "")
    payload = {
        "period": params.get(period, ""),
        "plan_id": plan_id,
    }

    if coupon:
        check_url = domain + params.get("check", "/api/v1/user/coupon/check")
        result = check(check_url, {"code": coupon, "plan_id": plan_id}, headers, retry)
        if not result:
            print("failed to renewal because coupon is valid")
            return False

        payload["coupon_code"] = coupon

    trade_no = order(order_url, payload, headers, retry)
    if not trade_no:
        print("renewal error because cannot order")
        return False

    payload = {"trade_no": trade_no, "method": method}
    success = payment(payment_url, payload, headers, retry)
    print("renewal {}, domain: {}".format("success" if success else "fail", domain))
    return success


def wrapper(args, reset: bool, retry: int) -> bool:
    return flow(args["domain"], args["param"], HEADER, reset, retry)


def main(reset: bool, retry: int) -> None:
    config = config_load(os.path.join(PATH, "config.json"))
    params = config.get("domains", [])
    for args in params:
        flag = args.get("renewal", True)
        if not flag:
            print("skip renewal, domain: {}".format(args.get("domain", "").strip()))
            continue
        wrapper(args, reset, retry)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-n", "--num", type=int, required=False, default=1, help="renewal times"
    )
    parser.add_argument(
        "-c",
        "--reset",
        dest="reset",
        action="store_true",
        default=False,
        help="reset traffic flow",
    )
    parser.add_argument(
        "-s",
        "--sleep",
        type=int,
        required=False,
        choices=range(11),
        default=5,
        help="sleep time",
    )
    parser.add_argument(
        "-r",
        "--retry",
        type=int,
        required=False,
        choices=range(5),
        default=3,
        help="retry if fail",
    )

    args = parser.parse_args()
    if args.reset:
        main(reset=True, retry=args.retry)
        sys.exit(0)

    for i in range(args.num):
        main(reset=False, retry=args.retry)
        delay = randint(0, 60 * args.sleep)
        print("第{}次续订完成，下次运行需等待{}秒".format(i + 1, delay))
        print()
        if i != args.num - 1:
            time.sleep(delay)
