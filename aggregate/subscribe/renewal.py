# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-04-05

import base64
import json
import os
import random
import re
import time
import traceback
import urllib
import urllib.parse
import urllib.request
import warnings
from dataclasses import dataclass
from datetime import datetime

import utils
from logger import logger

warnings.filterwarnings("ignore")

HEADER = {
    "user-agent": utils.USER_AGENT,
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9",
    "content-language": "zh-CN",
    "content-type": "application/x-www-form-urlencoded",
}

PATH = os.path.abspath(os.path.dirname(__file__))

PACKAGES = [
    "month_price",
    "quarter_price",
    "half_year_price",
    "year_price",
    "two_year_price",
    "three_year_price",
    "onetime_price",
]


@dataclass
class SubscribeInfo:
    plan_id: int
    renew_enable: bool
    reset_enable: bool
    used_rate: float
    expired_days: int
    package: str
    sub_url: str


@dataclass
class Plan:
    plan_id: int
    package: str
    renew: bool
    reset: bool
    trafficflow: float


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

    headers = {"user-agent": utils.USER_AGENT, "referer": domain}
    text, authorization = login(login_url, user_info, headers, retry)
    return utils.extract_cookie(text), authorization


def generate_headers(
    domain: str, cookies: str, authorization: str, headers: dict = None
) -> dict:
    if not headers:
        headers = {"user-agent": utils.USER_AGENT}

    if domain:
        headers["referer"] = domain
    if cookies:
        headers["cookie"] = cookies
    if authorization:
        headers["authorization"] = authorization

    return headers


def login(url: str, params: dict, headers: dict, retry: int = 3) -> tuple[str, str]:
    if not params:
        logger.error("[RenewalError] cannot login because parameters is empty")
        return "", ""

    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
        cookies, authorization = "", ""
        if response.getcode() == 200:
            cookies = response.getheader("Set-Cookie")
            try:
                data = json.loads(response.read().decode("UTF8")).get("data", {})
                authorization = data.get("auth_data", "")
            except:
                logger.error(response.read().decode("UTF8"))
        else:
            logger.info(response.read().decode("UTF8"))

        return cookies, authorization

    except Exception as e:
        logger.error(e)
        retry -= 1

        if retry > 0:
            return login(url, params, headers, retry)

        logger.error("[LoginError] URL: {}".format(utils.extract_domain(url)))
        return "", ""


def order(url: str, params: dict, headers: dict, retry: int = 3) -> str:
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
        trade_no = None
        if response.getcode() == 200:
            result = json.loads(response.read().decode("UTF8"))
            trade_no = result.get("data", None)
        else:
            logger.error(response.read().decode("UTF8"))

        return trade_no

    except Exception as e:
        logger.error(e)
        retry -= 1

        if retry > 0:
            return order(url, params, headers, retry)

        logger.error("[OrderError] URL: {}".format(utils.extract_domain(url)))


def fetch(url: str, headers: dict, retry: int = 3) -> str:
    try:
        request = urllib.request.Request(url, headers=headers, method="GET")
        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
        if response.getcode() != 200:
            logger.info(response.read().decode("UTF8"))
            return None

        data = json.loads(response.read().decode("UTF8"))
        # trade_nos = [x["trade_no"] for x in data if x["type"] == 2]
        for item in data["data"]:
            if item["status"] == 0:
                return item["trade_no"]

        return None

    except Exception as e:
        logger.error(e)
        retry -= 1

        if retry > 0:
            return fetch(url, headers, retry)

        logger.error("[FetchError] URL: {}".format(utils.extract_domain(url)))


def payment(url: str, params: dict, headers: dict, retry: int = 3) -> bool:
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
        success = False
        if response.getcode() == 200:
            result = json.loads(response.read().decode("UTF8"))
            success = result.get("data", False)
        else:
            logger.info(response.read().decode("UTF8"))

        return success

    except Exception as e:
        logger.error(e)
        retry -= 1

        if retry > 0:
            return payment(url, params, headers, retry)

        logger.error("[PaymentError] URL: {}".format(utils.extract_domain(url)))
        return False


def checkout(url: str, params: dict, headers: dict, retry: int = 3) -> bool:
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
        success = False
        if response.getcode() == 200:
            result = json.loads(response.read().decode("UTF8"))
            success = False if result.get("data", None) is None else True
        else:
            logger.info(response.read().decode("UTF8"))

        return success

    except Exception as e:
        logger.error(e)
        retry -= 1

        if retry > 0:
            return checkout(url, params, headers, retry)

        logger.error("[CheckError] URL: {}".format(utils.extract_domain(url)))
        return False


def get_payment_method(
    domain: str, cookies: str, authorization: str = "", retry: int = 3
) -> list:
    if not domain or (not cookies and not authorization):
        logger.error(
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
        logger.error(
            f"cannot get payment method because response is empty, domain: {domain}"
        )
        return []


def get_free_plan(
    domain: str, cookies: str, authorization: str = "", retry: int = 3
) -> Plan:
    if not domain or (not cookies and not authorization):
        logger.error(
            f"fetch free plans error, cookies and authorization is empty, domain: {domain}"
        )
        return None

    url = domain + "/api/v1/user/plan/fetch"
    headers = generate_headers(
        domain=domain, cookies=cookies, authorization=authorization
    )
    content = utils.http_get(url=url, headers=headers, retry=retry)
    if not content:
        return None
    try:
        plans = []
        data = json.loads(content).get("data", [])
        for plan in data:
            # 查找时间最长的免费套餐
            package = ""
            for p in PACKAGES:
                price = plan.get(p, None)
                if price is None or price > 0:
                    continue
                package = p

            if not package:
                continue

            renew_enable = plan.get("renew", 0) == 1
            reset_price = plan.get("reset_price", 1)
            reset_enable = False if reset_price is None else reset_price <= 0
            trafficflow = data.get("transfer_enable", 1)

            plans.append(
                Plan(
                    plan_id=plan.get("id", -1),
                    package=package,
                    renew=renew_enable,
                    reset=reset_enable,
                    trafficflow=trafficflow,
                )
            )
        if not plans:
            return None

        # 查找流量最多的免费套餐
        sorted(plans, key=lambda x: x.trafficflow, reverse=True)
        return plans[0]
    except:
        logger.error(
            f"cannot fetch free plans because response is empty, domain: {domain}"
        )
        return None


def get_subscribe_info(
    domain: str, cookies: str, authorization: str = "", retry: int = 3
) -> SubscribeInfo:
    if not domain or (not cookies and not authorization):
        logger.error(
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
        sub_url = data.get("subscribe_url", "").replace("\\", "")
        timestamp = data.get("expired_at", 1)
        # 如果为空, 则默认到2999/12/31 23:59:59
        timestamp = 32503651199 if not timestamp else timestamp
        expired_at = datetime.fromtimestamp(timestamp)
        today = datetime.fromtimestamp(time.time())
        expired_days = (expired_at - today).days
        used = data.get("d", 0)
        trafficflow = data.get("transfer_enable", 1)
        used_rate = round(used / trafficflow, 2)

        plan = data.get("plan", {})
        renew_enable = plan.get("renew", 0) == 1
        reset_price = plan.get("reset_price", 1)
        reset_enable = False if reset_price is None else reset_price <= 0

        package = ""
        for p in PACKAGES:
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
            sub_url=sub_url,
        )
    except:
        logger.error(
            f"cannot get subscribe information, domain: {domain}, response: {content}"
        )
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
            logger.error("not support renewal")
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
            logger.info("failed to renewal because coupon is valid")
            return False

        payload["coupon_code"] = coupon

    trade_no = order(order_url, payload, headers, retry)
    if not trade_no:
        logger.info("renewal error because cannot order")
        return False

    payload = {"trade_no": trade_no, "method": method}
    success = payment(payment_url, payload, headers, retry)
    return success


def add_traffic_flow(domain: str, params: dict) -> str:
    if not domain or not params:
        logger.error(f"[RenewalError] invalidate arguments")
        return ""
    try:
        email = base64.b64decode(params.get("email", ""))
        password = base64.b64decode(params.get("passwd", ""))
        cookies, authorization = get_cookies(
            domain=domain, username=email, password=password
        )
        subscribe = get_subscribe_info(
            domain=domain, cookies=cookies, authorization=authorization
        )
        if not subscribe:
            logger.info(f"[RenewalError] cannot fetch subscribe information")
            return ""

        plan_id = params.get("plan_id", subscribe.plan_id)
        package = params.get("package", subscribe.package)
        coupon_code = params.get("coupon_code", "")
        method = params.get("method", -1)
        if method <= 0:
            methods = get_payment_method(
                domain=domain, cookies=cookies, authorization=authorization
            )
            if not methods:
                method = 1
            else:
                method = random.choice(methods)

        payload = {
            "email": email,
            "passwd": password,
            "package": package,
            "plan_id": plan_id,
            "method": method,
            "coupon_code": coupon_code,
        }

        renew = params.get("enable", True)
        if renew and subscribe.reset_enable and subscribe.used_rate >= 0.8:
            success = flow(
                domain=domain,
                params=payload,
                reset=True,
                cookies=cookies,
                authorization=authorization,
            )
            logger.info(
                "reset {}, domain: {}".format("success" if success else "fail", domain)
            )
        else:
            logger.info(
                f"skip reset traffic plan, domain: {domain}\trenew: {renew}\tenable: {subscribe.reset_enable}\tused-rate: {subscribe.used_rate}"
            )
        if (
            renew
            and subscribe.renew_enable
            and (
                subscribe.expired_days <= 5
                or (not subscribe.reset_enable and subscribe.used_rate >= 0.8)
            )
        ):
            success = flow(
                domain=domain,
                params=payload,
                reset=False,
                cookies=cookies,
                authorization=authorization,
            )
            logger.info(
                "renew {}, domain: {}".format("success" if success else "fail", domain)
            )
        else:
            logger.info(
                f"skip renew traffic plan, domain: {domain}\trenew: {renew}\tenable: {subscribe.renew_enable}\texpired-days: {subscribe.expired_days}"
            )

        return subscribe.sub_url
    except:
        traceback.print_exc()
        return ""
