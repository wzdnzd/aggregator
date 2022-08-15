# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-04-05

import json
import os
import re
import ssl
import time
import urllib
import urllib.parse
import urllib.request
import warnings
from dataclasses import dataclass
from datetime import datetime

import utils

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


@dataclass
class SubscribeInfo:
    plan_id: int
    renew_enable: bool
    reset_enable: bool
    used_rate: float
    expired_days: int
    package: str
    token: str


def get_cookies(
    domain: str, username: str, password: str, retry: int = 3
) -> tuple[str, str]:
    login_url = domain + "/api/v1/passport/auth/login"
    headers = HEADER
    headers["origin"] = domain
    headers["referer"] = domain + "/"

    user_info = {
        "email": username,
        "password": password,
    }

    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36 Edg/100.0.1185.39",
        "referer": domain,
    }

    text, authorization = login(login_url, user_info, headers, retry)
    return utils.extract_cookie(text), authorization


def generate_headers(
    domain: str, cookies: str, authorization: str, headers: dict = None
) -> dict:
    if not headers:
        headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36 Edg/100.0.1185.39"
        }

    if domain:
        headers["referer"] = domain
    if cookies:
        headers["cookie"] = cookies
    if authorization:
        headers["authorization"] = authorization

    return headers


def login(url: str, params: dict, headers: dict, retry: int = 3) -> tuple[str, str]:
    if not params:
        print("[RenewalError] cannot login because parameters is empty")
        return "", ""

    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        cookies, authorization = "", ""
        if response.getcode() == 200:
            cookies = response.getheader("Set-Cookie")
            try:
                data = json.loads(response.read().decode("UTF8")).get("data", {})
                authorization = data.get("auth_data", "")
            except:
                print(response.read().decode("UTF8"))
        else:
            print(response.read().decode("UTF8"))

        return cookies, authorization

    except Exception as e:
        print(str(e))
        retry -= 1

        if retry > 0:
            return login(url, params, headers, retry)

        print("[LoginError] URL: {}".format(utils.extract_domain(url)))
        return "", ""


def order(url: str, params: dict, headers: dict, retry: int = 3) -> str:
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        trade_no = None
        if response.getcode() == 200:
            result = json.loads(response.read().decode("UTF8"))
            trade_no = result.get("data", None)
        else:
            print(response.read().decode("UTF8"))

        return trade_no

    except Exception as e:
        print(str(e))
        retry -= 1

        if retry > 0:
            return order(url, params, headers, retry)

        print("[OrderError] URL: {}".format(utils.extract_domain(url)))


def fetch(url: str, headers: dict, retry: int = 3) -> str:
    try:
        request = urllib.request.Request(url, headers=headers, method="GET")
        response = urllib.request.urlopen(request, timeout=10, context=CTX)
        if response.getcode() != 200:
            print(response.read().decode("UTF8"))
            return None

        data = json.loads(response.read().decode("UTF8"))
        # trade_nos = [x["trade_no"] for x in data if x["type"] == 2]
        for item in data["data"]:
            if item["status"] == 0:
                return item["trade_no"]

        return None

    except Exception as e:
        print(str(e))
        retry -= 1

        if retry > 0:
            return fetch(url, headers, retry)

        print("[FetchError] URL: {}".format(utils.extract_domain(url)))


def payment(url: str, params: dict, headers: dict, retry: int = 3) -> bool:
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

        print("[PaymentError] URL: {}".format(utils.extract_domain(url)))
        return False


def checkout(url: str, params: dict, headers: dict, retry: int = 3) -> bool:
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
            return checkout(url, params, headers, retry)

        print("[CheckError] URL: {}".format(utils.extract_domain(url)))
        return False


def get_payment_method(
    domain: str, cookies: str, authorization: str = "", retry: int = 3
) -> list:
    if not domain or not cookies:
        print(
            f"query payment method error, cookies and authorization is empty, domain: {domain}"
        )
        return []

    url = domain + "/api/v1/user/order/getPaymentMethod"
    headers = generate_headers(
        domain=domain, cookies=cookies, authorization=authorization
    )

    content = utils.http_get(url=url, headers=headers, retry=retry)
    if not content:
        return []
    try:
        data = json.loads(content).get("data", [])
        methods = [item.get("id") for item in data if item.get("id", -1) >= 0]
        return methods
    except:
        print(f"cannot get payment method because response is empty, domain: {domain}")
        return []


def get_subscribe_info(
    domain: str, cookies: str, authorization: str = "", retry: int = 3
) -> SubscribeInfo:
    if not domain or (not cookies and not authorization):
        print(
            f"query subscribe information error, cookies and authorization is empty, domain: {domain}"
        )
        return None

    url = domain + "/api/v1/user/getSubscribe"
    headers = generate_headers(
        domain=domain, cookies=cookies, authorization=authorization
    )

    content = utils.http_get(url=url, headers=headers, retry=retry)
    if not content:
        return None

    try:
        data = json.loads(content).get("data", {})
        if not data:
            return None

        plan_id = data.get("plan_id", 1)
        token = data.get("token", "")
        expired_at = datetime.fromtimestamp(data.get("expired_at", 1))
        today = datetime.fromtimestamp(time.time())
        expired_days = (expired_at - today).days
        used = data.get("d", 0)
        trafficflow = data.get("transfer_enable", 1)
        used_rate = round(used / trafficflow, 2)

        plan = data.get("plan", {})
        renew_enable = plan.get("renew", 0) == 1
        reset_price = plan.get("reset_price", 1)
        reset_enable = False if reset_price is None else reset_price <= 0
        packages = [
            "month_price",
            "quarter_price",
            "half_year_price",
            "year_price",
            "two_year_price",
            "three_year_price",
            "onetime_price",
        ]

        package = ""
        for p in packages:
            price = plan.get(p, None)
            if price is not None and price <= 0:
                package = p
                break

        return SubscribeInfo(
            plan_id=plan_id,
            renew_enable=renew_enable,
            reset_enable=reset_enable,
            used_rate=used_rate,
            expired_days=expired_days,
            package=package,
            token=token,
        )
    except:
        print(f"cannot get payment method because response is empty, domain: {domain}")
        return None


def flow(
    domain: str,
    params: dict,
    reset: bool = False,
    retry: int = 3,
    headers: dict = HEADER,
    cookies: str = "",
    authorization: str = "",
) -> bool:
    domain = domain.strip()
    regex = "(?i)^(https?:\\/\\/)?(www.)?([^\\/]+\\.[^.]*$)"
    if not re.search(regex, domain):
        return False

    fetch_url = domain + params.get("fetch", "/api/v1/user/order/fetch")
    order_url = domain + params.get("order", "/api/v1/user/order/save")
    payment_url = domain + params.get("payment", "/api/v1/user/order/checkout")
    method = params.get("method", 1)
    coupon = params.get("coupon_code", "")

    headers["origin"] = domain
    headers["referer"] = domain + "/"

    if not cookies.strip() and not authorization.strip():
        user_info = {
            "email": params.get("email", ""),
            "password": params.get("passwd", ""),
        }

        login_url = domain + params.get("login", "/api/v1/passport/auth/login")
        text, authorization = login(login_url, user_info, headers, retry)
        cookies = utils.extract_cookie(text)

    if len(cookies) <= 0 and not authorization:
        return False

    headers = generate_headers(
        domain=domain, cookies=cookies, authorization=authorization, headers=headers
    )

    trade_no = fetch(fetch_url, headers, retry)

    if trade_no:
        payload = {"trade_no": trade_no, "method": method}
        if coupon:
            payload["coupon_code"] = coupon
        if not payment(payment_url, payload, headers, retry):
            return False
    if reset:
        package = "reset_price"
    else:
        package = params.get("package", "")
        if not package:
            print("not support renewal")
            return False

    plan_id = params.get("plan_id", 1)
    payload = {
        "period": package,
        "plan_id": plan_id,
    }

    if coupon:
        check_url = domain + params.get("check", "/api/v1/user/coupon/check")
        result = checkout(
            check_url, {"code": coupon, "plan_id": plan_id}, headers, retry
        )
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
    return success
