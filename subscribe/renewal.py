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
from copy import deepcopy
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
    reset_day: int


@dataclass
class Plan:
    plan_id: int
    package: str
    renew: bool
    reset: bool
    trafficflow: float


def get_cookies(
    domain: str, username: str, password: str, retry: int = 3, api_prefix: str = "", jsonify: bool = False
) -> tuple[str, str]:
    if utils.isblank(domain) or utils.isblank(username) or utils.isblank(password):
        return "", ""

    login_url = domain + utils.get_subpath(api_prefix) + "passport/auth/login"
    headers = deepcopy(HEADER)
    headers["origin"] = domain
    headers["referer"] = domain + "/"

    user_info = {
        "email": username,
        "password": password,
    }

    headers = {"user-agent": utils.USER_AGENT, "referer": domain}
    text, authorization = login(login_url, user_info, headers, retry, jsonify)
    return utils.extract_cookie(text), authorization


def generate_headers(domain: str, cookies: str, authorization: str, headers: dict = None) -> dict:
    if not headers:
        headers = {"user-agent": utils.USER_AGENT}

    if domain:
        headers["referer"] = domain
    if cookies:
        headers["cookie"] = cookies
    if authorization:
        headers["authorization"] = authorization

    return headers


def login(url: str, params: dict, headers: dict, retry: int = 3, jsonify: bool = False) -> tuple[str, str]:
    if not params:
        logger.error("[RenewalError] cannot login because parameters is empty")
        return "", ""

    try:
        if jsonify:
            headers["Content-Type"] = "application/json"
            data = json.dumps(params).encode(encoding="UTF8")
        else:
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

    except:
        retry -= 1
        if retry > 0:
            return login(url, params, headers, retry, jsonify)

        logger.error("[LoginError] URL: {}".format(utils.extract_domain(url)))
        return "", ""


def order(url: str, params: dict, headers: dict, retry: int = 3, jsonify: bool = False) -> str:
    try:
        if jsonify:
            headers["Content-Type"] = "application/json"
            data = json.dumps(params).encode(encoding="UTF8")
        else:
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

    except:
        retry -= 1
        if retry > 0:
            return order(url, params, headers, retry, jsonify)

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

    except:
        retry -= 1
        if retry > 0:
            return fetch(url, headers, retry)

        logger.error("[FetchError] URL: {}".format(utils.extract_domain(url)))


def payment(url: str, params: dict, headers: dict, retry: int = 3, jsonify: bool = False) -> bool:
    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        if jsonify:
            headers["Content-Type"] = "application/json"
            data = json.dumps(params).encode(encoding="UTF8")

        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)

        success = False
        if response.getcode() == 200:
            result = json.loads(response.read().decode("UTF8"))
            success = result.get("data", False)
        else:
            logger.info(response.read().decode("UTF8"))

        return success

    except:
        retry -= 1
        if retry > 0:
            return payment(url, params, headers, retry, jsonify)

        logger.error("[PaymentError] URL: {}".format(utils.extract_domain(url)))
        return False


def checkout(
    domain: str,
    coupon: str,
    headers: dict,
    planid: int = -1,
    retry: int = 3,
    link: str = "",
    api_prefix: str = "",
    jsonify: bool = False,
) -> dict:
    if utils.isblank(domain) or utils.isblank(coupon):
        return {}

    link = utils.get_subpath(api_prefix) + "user/coupon/check" if utils.isblank(link) else link
    try:
        url = f"{domain}{link}"
        params = {"code": coupon}
        if type(planid) == int and planid >= 0:
            params["plan_id"] = planid

        if jsonify:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(params).encode(encoding="UTF8")
        else:
            payload = urllib.parse.urlencode(params).encode(encoding="UTF8")

        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)

        data = {}
        if response.getcode() == 200:
            result = json.loads(response.read().decode("UTF8"))
            data = result.get("data", {})
        else:
            logger.info(response.read().decode("UTF8"))

        return data
    except Exception:
        retry -= 1
        if retry > 0:
            return checkout(
                domain=domain,
                coupon=coupon,
                headers=headers,
                planid=planid,
                retry=retry,
                link=link,
                api_prefix=api_prefix,
                jsonify=jsonify,
            )

        logger.error("[CheckError] URL: {}".format(utils.extract_domain(url)))
        return {}


def get_payment_method(
    domain: str, cookies: str, authorization: str = "", retry: int = 3, api_prefix: str = ""
) -> list:
    if not domain or (not cookies and not authorization):
        logger.error(f"query payment method error, cookies and authorization is empty, domain: {domain}")
        return []

    url = domain + utils.get_subpath(api_prefix) + "user/order/getPaymentMethod"
    headers = generate_headers(domain=domain, cookies=cookies, authorization=authorization)

    content = utils.http_get(url=url, headers=headers, retry=retry)
    if not content:
        return []
    try:
        data = json.loads(content).get("data", [])
        methods = [item.get("id") for item in data if item.get("id", -1) >= 0]
        return methods
    except:
        logger.error(f"cannot get payment method because response is empty, domain: {domain}")
        return []


def unclosed_ticket(domain: str, headers: dict, api_prefix: str = "") -> tuple[int, int, str]:
    if utils.isblank(domain) or not headers:
        logger.info(f"[TicketError] cannot fetch tickets because invalidate arguments, domain: {domain}")
        return -1, -1, ""

    url = domain + utils.get_subpath(api_prefix) + "user/ticket/fetch"
    content = utils.http_get(url=url, headers=headers)
    try:
        tickets = json.loads(content).get("data", [])
        tid, timestamp, subject = -1, -1, ""
        for ticket in tickets:
            status = ticket.get("status", 0)
            if status == 0:
                tid = ticket.get("id", -1)
                timestamp = ticket.get("updated_at", -1)
                subject = ticket.get("subject", "")
                break

        return tid, timestamp, subject
    except:
        logger.error(f"[TicketError] failed fetch last ticket, domain: {domain}, content: {content}")
        return -1, -1, ""


def close_ticket(
    domain: str, tid: int, headers: dict, retry: int = 3, api_prefix: str = "", jsonify: bool = False
) -> bool:
    if utils.isblank(domain) or tid < 0 or not headers or retry <= 0:
        logger.info(f"[TicketError] cannot close ticket because invalidate arguments, domain: {domain}, tid: {tid}")

    url = domain + utils.get_subpath(api_prefix) + "user/ticket/close"
    params = {"id": tid}

    try:
        data = urllib.parse.urlencode(params).encode(encoding="UTF8")
        if jsonify:
            headers["Content-Type"] = "application/json"
            data = json.dumps(params).encode(encoding="UTF8")

        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)

        if response.getcode() == 200:
            content = response.read().decode("UTF8")
            try:
                return json.loads(content).get("data", False)
            except:
                logger.error(f"[TicketError] failed submit ticket, domain: {domain}, message: {content}")

        return False

    except:
        return close_ticket(
            domain=domain,
            tid=tid,
            headers=headers,
            retry=retry - 1,
            api_prefix=api_prefix,
            jsonify=jsonify,
        )


def submit_ticket(
    domain: str,
    cookies: str,
    ticket: dict,
    authorization: str = "",
    retry: int = 3,
    api_prefix: str = "",
    jsonify: bool = False,
) -> bool:
    if retry <= 0:
        logger.error(f"[TicketError] achieved max retry when submit ticket, domain: {domain}")
        return False

    if utils.isblank(domain) or (utils.isblank(cookies) and utils.isblank(authorization)):
        logger.error(f"[TicketError] submit ticket error, cookies and authorization is empty, domain: {domain}")
        return False

    if not ticket or type(ticket) != dict:
        logger.info(f"[TicketError] skip submit ticket because subject or message is empty, domain: {domain}")
        return False

    subject = ticket.get("subject", "")
    message = ticket.get("message", "")
    level = ticket.get("level", 1)
    level = level if level in [0, 1, 2] else 1

    if utils.isblank(subject) or utils.isblank(message):
        logger.info(f"[TicketError] skip submit ticket because subject or message is empty, domain: {domain}")
        return False

    headers = generate_headers(domain=domain, cookies=cookies, authorization=authorization)

    # check last unclosed ticket
    tid, timestamp, title = unclosed_ticket(domain=domain, headers=headers, api_prefix=api_prefix)
    if tid > 0 and timestamp > 0:
        # do not submit ticket if there are unclosed tickets in the last three days
        if time.time() - timestamp < 259200000:
            date = datetime.fromtimestamp(timestamp)
            logger.info(
                f"[TicketInfo] don't submit a ticket because found an unclosed ticket in the last three days, domain: {domain}, tid: {tid}, subject: {title}, time: {date}"
            )
            return False

        logger.info(
            f"[TicketInfo] found a unclosed ticket, domain: {domain}, tid: {tid}, subject: {title}, try close it now"
        )
        success = close_ticket(domain=domain, tid=tid, headers=headers, api_prefix=api_prefix, jsonify=jsonify)
        if not success:
            logger.error(
                f"[TicketError] cannot submit a ticket because found an unclosed ticket but cannot close it, domain: {domain}, tid: {tid}, subject: {title}"
            )
            return False

    url = domain + utils.get_subpath(api_prefix) + "user/ticket/save"
    params = {"subject": subject, "level": level, "message": message}

    try:
        if jsonify:
            headers["Content-Type"] = "application/json"
            data = json.dumps(params).encode(encoding="UTF8")
        else:
            data = urllib.parse.urlencode(params).encode(encoding="UTF8")

        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)

        if response.getcode() == 200:
            content = response.read().decode("UTF8")
            try:
                return json.loads(content).get("data", False)
            except:
                logger.error(f"[TicketError] failed submit ticket, domain: {domain}, message: {content}")

        return False

    except:
        return submit_ticket(
            domain=domain,
            cookies=cookies,
            ticket=ticket,
            authorization=authorization,
            retry=retry - 1,
            api_prefix=api_prefix,
            jsonify=jsonify,
        )


def get_free_plan(
    domain: str,
    cookies: str,
    authorization: str = "",
    retry: int = 3,
    coupon: str = "",
    api_prefix: str = "",
    jsonify: bool = False,
) -> Plan:
    if not domain or (not cookies and not authorization):
        logger.error(f"fetch free plans error, cookies and authorization is empty, domain: {domain}")
        return None

    api_prefix = utils.get_subpath(api_prefix)
    url = domain + api_prefix + "user/plan/fetch"
    headers = generate_headers(domain=domain, cookies=cookies, authorization=authorization)
    content = utils.http_get(url=url, headers=headers, retry=retry)
    if not content:
        return None

    discount = None
    if not utils.isblank(coupon):
        discount = checkout(
            domain=domain,
            coupon=coupon,
            headers=headers,
            retry=retry,
            api_prefix=api_prefix,
            jsonify=jsonify,
        )

    try:
        plans = []
        data = json.loads(content).get("data", [])
        for plan in data:
            # 查找时间最长的免费套餐
            package, planid = "", plan.get("id", -1)
            for p in PACKAGES:
                price = plan.get(p, None)
                if not isfree(planid=str(planid), package=p, price=price, discount=discount):
                    continue
                package = p

            if not package:
                continue

            renew_enable = plan.get("renew", 0) == 1
            reset_price = plan.get("reset_price", 1)
            reset_enable = False if reset_price is None else reset_price <= 0
            trafficflow = plan.get("transfer_enable", 1)

            plans.append(
                Plan(
                    plan_id=planid,
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
        logger.error(f"cannot fetch free plans because response is empty, domain: {domain}")
        return None


def isfree(planid: str, package: str, price: float, discount: dict) -> bool:
    # 不存在的套餐
    if utils.isblank(planid) or utils.isblank(package) or price is None:
        return False

    # 套餐价格为0
    if price <= 0:
        return True

    # 没有优惠且套餐价格大于0
    if not discount and price > 0:
        return False

    # 限定套餐范围
    planids = discount.get("limit_plan_ids", None)
    # 限定周期
    packages = discount.get("limit_period", None)

    # 不在优惠范围内
    if (planids and planid not in planids) or (packages and package not in packages):
        return False

    # 优惠类型 1代表实际金额，2代表比例
    coupontype = discount.get("type", 1)
    # 优惠额度
    couponvalue = discount.get("value", 0)

    # 如果优惠金额与套餐价相等或者优惠比例为100(%)，返回True
    if coupontype == 1:
        return couponvalue == price
    return couponvalue == 100


def get_subscribe_info(
    domain: str, cookies: str, authorization: str = "", retry: int = 3, api_prefix: str = ""
) -> SubscribeInfo:
    if not domain or (not cookies and not authorization):
        logger.error(f"query subscribe information error, cookies and authorization is empty, domain: {domain}")
        return None

    url = domain + utils.get_subpath(api_prefix) + "user/getSubscribe"
    headers = generate_headers(domain=domain, cookies=cookies, authorization=authorization)

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
        reset_day = data.get("reset_day", 365)
        reset_day = 365 if (reset_day is None or reset_day < 0) else reset_day
        used = data.get("d", 0)
        trafficflow = data.get("transfer_enable", 1)
        used_rate = 0.00 if not trafficflow else round(used / trafficflow, 2)

        plan = data.get("plan", {})
        renew_enable = plan.get("renew", 0) == 1 if plan else False
        reset_price = plan.get("reset_price", 1) if plan else 1
        reset_enable = False if reset_price is None else reset_price <= 0

        package = ""
        if isinstance(plan, dict):
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
            reset_day=reset_day,
        )
    except:
        logger.error(f"cannot get subscribe information, domain: {domain}, response: {content}")
        return None


def flow(
    domain: str,
    params: dict,
    reset: bool = False,
    retry: int = 3,
    cookies: str = "",
    authorization: str = "",
) -> bool:
    domain = domain.strip()
    regex = "(?i)^(https?:\\/\\/)?(www.)?([^\\/]+\\.[^.]*$)"
    if not re.search(regex, domain):
        return False

    api_prefix = utils.get_subpath(params.get("api_prefix", ""))
    jsonify = params.get("jsonify", False)

    fetch_url = domain + params.get("fetch", f"{api_prefix}user/order/fetch")
    order_url = domain + params.get("order", f"{api_prefix}user/order/save")
    payment_url = domain + params.get("payment", f"{api_prefix}user/order/checkout")
    method = params.get("method", 1)
    coupon = params.get("coupon_code", "")

    headers = deepcopy(HEADER)
    headers["origin"] = domain
    headers["referer"] = domain + "/"

    if not cookies.strip() and not authorization.strip():
        user_info = {
            "email": params.get("email", ""),
            "password": params.get("passwd", ""),
        }

        login_url = domain + params.get("login", f"{api_prefix}passport/auth/login")
        text, authorization = login(login_url, user_info, headers, retry, jsonify)
        cookies = utils.extract_cookie(text)

    if len(cookies) <= 0 and not authorization:
        return False

    headers = generate_headers(domain=domain, cookies=cookies, authorization=authorization, headers=headers)
    trade_no = fetch(fetch_url, headers, retry)

    if trade_no:
        payload = {"trade_no": trade_no, "method": method}
        if coupon:
            payload["coupon_code"] = coupon
        if not payment(payment_url, payload, headers, retry, jsonify):
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
        link = params.get("check", f"{api_prefix}user/coupon/check")
        result = checkout(
            domain=domain,
            coupon=coupon,
            headers=headers,
            planid=plan_id,
            retry=retry,
            link=link,
            jsonify=jsonify,
        )
        if not result:
            logger.info("failed to renewal because coupon is valid")
            return False

        payload["coupon_code"] = coupon

    trade_no = order(order_url, payload, headers, retry, jsonify)
    if not trade_no:
        logger.info("renewal error because cannot order")
        return False

    payload = {"trade_no": trade_no, "method": method}
    success = payment(payment_url, payload, headers, retry, jsonify)
    return success


def add_traffic_flow(domain: str, params: dict, jsonify: bool = False) -> str:
    if not domain or not params:
        logger.error(f"[RenewalError] invalidate arguments")
        return ""
    try:
        email = base64.b64decode(params.get("email", "")).decode()
        password = base64.b64decode(params.get("passwd", "")).decode()
        if utils.isblank(email) or utils.isblank(password):
            logger.info(f"[RenewalError] email or password cannot be empty, domain: {domain}")
            return ""

        api_prefix = params.get("api_prefix", "")
        cookies, authorization = get_cookies(
            domain=domain,
            username=email,
            password=password,
            api_prefix=api_prefix,
            jsonify=jsonify,
        )
        subscribe = get_subscribe_info(
            domain=domain,
            cookies=cookies,
            authorization=authorization,
            api_prefix=api_prefix,
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
                domain=domain,
                cookies=cookies,
                authorization=authorization,
                api_prefix=api_prefix,
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
            "api_prefix": api_prefix,
            "jsonify": jsonify,
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
            logger.info("reset {}, domain: {}".format("success" if success else "fail", domain))
        else:
            logger.info(
                f"skip reset traffic plan, domain: {domain}\trenew: {renew}\tenable: {subscribe.reset_enable}\tused-rate: {subscribe.used_rate}"
            )

        subscribe.renew_enable = subscribe.renew_enable and (
            not utils.isblank(package) or not utils.isblank(coupon_code)
        )
        if (
            renew
            and subscribe.renew_enable
            and (subscribe.expired_days <= 5 or (not subscribe.reset_enable and subscribe.used_rate >= 0.8))
        ):
            success = flow(
                domain=domain,
                params=payload,
                reset=False,
                cookies=cookies,
                authorization=authorization,
            )
            logger.info("renew {}, domain: {}".format("success" if success else "fail", domain))
        else:
            logger.info(
                f"skip renew traffic plan, domain: {domain}\trenew: {renew}\tenable: {subscribe.renew_enable}\texpired-days: {subscribe.expired_days}"
            )

        # 提交工单重置流量
        ticket = params.get("ticket", {})
        if ticket and type(ticket) == dict:
            enable = ticket.pop("enable", True)
            autoreset = ticket.pop("autoreset", False)
            # 过期时间 <= 5 或者 流量使用例 >= 0.8 或者 重置日期 <= 1 且不会自动重置时提交工单
            if enable and (
                (subscribe.expired_days <= 5 or subscribe.used_rate >= 0.8)
                or (not autoreset and subscribe.reset_day <= 1)
            ):
                success = submit_ticket(
                    domain=domain,
                    cookies=cookies,
                    ticket=ticket,
                    authorization=authorization,
                    api_prefix=api_prefix,
                    jsonify=jsonify,
                )

                logger.info(f"ticket submit {'successed' if success else 'failed'}, domain: {domain}")

        return subscribe.sub_url
    except:
        traceback.print_exc()
        return ""
