# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-07-12

import json
import math
import os
import random
import re
import socket
import urllib
from collections import defaultdict

import utils
from geoip2 import database
from logger import logger

# ISO国家代码到中文国家名称的映射
ISO_TO_CHINESE = {
    "AD": "安道尔",
    "AE": "阿联酋",
    "AF": "阿富汗",
    "AG": "安提瓜和巴布达",
    "AI": "安圭拉",
    "AL": "阿尔巴尼亚",
    "AM": "亚美尼亚",
    "AO": "安哥拉",
    "AR": "阿根廷",
    "AS": "美属萨摩亚",
    "AT": "奥地利",
    "AU": "澳大利亚",
    "AW": "阿鲁巴",
    "AX": "奥兰群岛",
    "AZ": "阿塞拜疆",
    "BA": "波黑",
    "BB": "巴巴多斯",
    "BD": "孟加拉国",
    "BE": "比利时",
    "BF": "布基纳法索",
    "BG": "保加利亚",
    "BH": "巴林",
    "BI": "布隆迪",
    "BJ": "贝宁",
    "BL": "圣巴泰勒米",
    "BM": "百慕大",
    "BN": "文莱",
    "BO": "玻利维亚",
    "BQ": "荷兰加勒比区",
    "BR": "巴西",
    "BS": "巴哈马",
    "BT": "不丹",
    "BV": "布韦岛",
    "BW": "博茨瓦纳",
    "BY": "白俄罗斯",
    "BZ": "伯利兹",
    "CA": "加拿大",
    "CC": "科科斯群岛",
    "CD": "刚果民主共和国",
    "CF": "中非",
    "CG": "刚果共和国",
    "CH": "瑞士",
    "CI": "科特迪瓦",
    "CK": "库克群岛",
    "CL": "智利",
    "CM": "喀麦隆",
    "CN": "中国",
    "CO": "哥伦比亚",
    "CR": "哥斯达黎加",
    "CU": "古巴",
    "CV": "佛得角",
    "CW": "库拉索",
    "CX": "圣诞岛",
    "CY": "塞浦路斯",
    "CZ": "捷克",
    "DE": "德国",
    "DJ": "吉布提",
    "DK": "丹麦",
    "DM": "多米尼克",
    "DO": "多米尼加",
    "DZ": "阿尔及利亚",
    "EC": "厄瓜多尔",
    "EE": "爱沙尼亚",
    "EG": "埃及",
    "EH": "西撒哈拉",
    "ER": "厄立特里亚",
    "ES": "西班牙",
    "ET": "埃塞俄比亚",
    "FI": "芬兰",
    "FJ": "斐济",
    "FK": "福克兰群岛",
    "FM": "密克罗尼西亚",
    "FO": "法罗群岛",
    "FR": "法国",
    "GA": "加蓬",
    "GB": "英国",
    "GD": "格林纳达",
    "GE": "格鲁吉亚",
    "GF": "法属圭亚那",
    "GG": "根西岛",
    "GH": "加纳",
    "GI": "直布罗陀",
    "GL": "格陵兰",
    "GM": "冈比亚",
    "GN": "几内亚",
    "GP": "瓜德罗普",
    "GQ": "赤道几内亚",
    "GR": "希腊",
    "GS": "南乔治亚和南桑威奇群岛",
    "GT": "危地马拉",
    "GU": "关岛",
    "GW": "几内亚比绍",
    "GY": "圭亚那",
    "HK": "香港",
    "HM": "赫德岛和麦克唐纳群岛",
    "HN": "洪都拉斯",
    "HR": "克罗地亚",
    "HT": "海地",
    "HU": "匈牙利",
    "ID": "印度尼西亚",
    "IE": "爱尔兰",
    "IL": "以色列",
    "IM": "马恩岛",
    "IN": "印度",
    "IO": "英属印度洋领地",
    "IQ": "伊拉克",
    "IR": "伊朗",
    "IS": "冰岛",
    "IT": "意大利",
    "JE": "泽西岛",
    "JM": "牙买加",
    "JO": "约旦",
    "JP": "日本",
    "KE": "肯尼亚",
    "KG": "吉尔吉斯斯坦",
    "KH": "柬埔寨",
    "KI": "基里巴斯",
    "KM": "科摩罗",
    "KN": "圣基茨和尼维斯",
    "KP": "朝鲜",
    "KR": "韩国",
    "KW": "科威特",
    "KY": "开曼群岛",
    "KZ": "哈萨克斯坦",
    "LA": "老挝",
    "LB": "黎巴嫩",
    "LC": "圣卢西亚",
    "LI": "列支敦士登",
    "LK": "斯里兰卡",
    "LR": "利比里亚",
    "LS": "莱索托",
    "LT": "立陶宛",
    "LU": "卢森堡",
    "LV": "拉脱维亚",
    "LY": "利比亚",
    "MA": "摩洛哥",
    "MC": "摩纳哥",
    "MD": "摩尔多瓦",
    "ME": "黑山",
    "MF": "法属圣马丁",
    "MG": "马达加斯加",
    "MH": "马绍尔群岛",
    "MK": "北马其顿",
    "ML": "马里",
    "MM": "缅甸",
    "MN": "蒙古",
    "MO": "澳门",
    "MP": "北马里亚纳群岛",
    "MQ": "马提尼克",
    "MR": "毛里塔尼亚",
    "MS": "蒙特塞拉特",
    "MT": "马耳他",
    "MU": "毛里求斯",
    "MV": "马尔代夫",
    "MW": "马拉维",
    "MX": "墨西哥",
    "MY": "马来西亚",
    "MZ": "莫桑比克",
    "NA": "纳米比亚",
    "NC": "新喀里多尼亚",
    "NE": "尼日尔",
    "NF": "诺福克岛",
    "NG": "尼日利亚",
    "NI": "尼加拉瓜",
    "NL": "荷兰",
    "NO": "挪威",
    "NP": "尼泊尔",
    "NR": "瑙鲁",
    "NU": "纽埃",
    "NZ": "新西兰",
    "OM": "阿曼",
    "PA": "巴拿马",
    "PE": "秘鲁",
    "PF": "法属波利尼西亚",
    "PG": "巴布亚新几内亚",
    "PH": "菲律宾",
    "PK": "巴基斯坦",
    "PL": "波兰",
    "PM": "圣皮埃尔和密克隆",
    "PN": "皮特凯恩群岛",
    "PR": "波多黎各",
    "PS": "巴勒斯坦",
    "PT": "葡萄牙",
    "PW": "帕劳",
    "PY": "巴拉圭",
    "QA": "卡塔尔",
    "RE": "留尼汪",
    "RO": "罗马尼亚",
    "RS": "塞尔维亚",
    "RU": "俄罗斯",
    "RW": "卢旺达",
    "SA": "沙特阿拉伯",
    "SB": "所罗门群岛",
    "SC": "塞舌尔",
    "SD": "苏丹",
    "SE": "瑞典",
    "SG": "新加坡",
    "SH": "圣赫勒拿",
    "SI": "斯洛文尼亚",
    "SJ": "斯瓦尔巴和扬马延",
    "SK": "斯洛伐克",
    "SL": "塞拉利昂",
    "SM": "圣马力诺",
    "SN": "塞内加尔",
    "SO": "索马里",
    "SR": "苏里南",
    "SS": "南苏丹",
    "ST": "圣多美和普林西比",
    "SV": "萨尔瓦多",
    "SX": "荷属圣马丁",
    "SY": "叙利亚",
    "SZ": "斯威士兰",
    "TC": "特克斯和凯科斯群岛",
    "TD": "乍得",
    "TF": "法属南部领地",
    "TG": "多哥",
    "TH": "泰国",
    "TJ": "塔吉克斯坦",
    "TK": "托克劳",
    "TL": "东帝汶",
    "TM": "土库曼斯坦",
    "TN": "突尼斯",
    "TO": "汤加",
    "TR": "土耳其",
    "TT": "特立尼达和多巴哥",
    "TV": "图瓦卢",
    "TW": "台湾",
    "TZ": "坦桑尼亚",
    "UA": "乌克兰",
    "UG": "乌干达",
    "UM": "美国本土外小岛屿",
    "US": "美国",
    "UY": "乌拉圭",
    "UZ": "乌兹别克斯坦",
    "VA": "梵蒂冈",
    "VC": "圣文森特和格林纳丁斯",
    "VE": "委内瑞拉",
    "VG": "英属维尔京群岛",
    "VI": "美属维尔京群岛",
    "VN": "越南",
    "VU": "瓦努阿图",
    "WF": "瓦利斯和富图纳",
    "WS": "萨摩亚",
    "YE": "也门",
    "YT": "马约特",
    "ZA": "南非",
    "ZM": "赞比亚",
    "ZW": "津巴布韦",
}


def download_mmdb(repo: str, target: str, filepath: str, retry: int = 3) -> bool:
    """
    Download GeoLite2-City.mmdb from github release
    """
    repo = utils.trim(text=repo)
    if not repo or len(repo.split("/", maxsplit=1)) != 2:
        logger.error(f"invalid github repo name: {repo}")
        return False

    target = utils.trim(text=target)
    if not target:
        logger.error("invalid download target")
        return False

    # extract download url from github release page
    release_api = f"https://api.github.com/repos/{repo}/releases/latest?per_page=1"

    assets, content = None, utils.http_get(url=release_api)
    try:
        data = json.loads(content)
        assets = data.get("assets", [])
    except:
        logger.error(f"failed download {target} due to cannot extract download url through Github API")

    if not assets or not isinstance(assets, list):
        logger.error(f"no assets found for {target} in github release")
        return False

    download_url = ""
    for asset in assets:
        if asset.get("name", "") == target:
            download_url = asset.get("browser_download_url", "")
            break

    if not download_url:
        logger.error(f"no download url found for {target} in github release")
        return False

    return download(download_url, filepath, target, retry)


def download(url: str, filepath: str, filename: str, retry: int = 3) -> bool:
    """Download file from url to filepath with filename"""

    if retry < 0:
        logger.error(f"archieved max retry count for download, url: {url}")
        return False

    url = utils.trim(text=url)
    if not url:
        logger.error("invalid download url")
        return False

    filepath = utils.trim(text=filepath)
    if not filepath:
        logger.error(f"invalid save filepath, url: {url}")
        return False

    filename = utils.trim(text=filename)
    if not filename:
        logger.error(f"invalid save filename, url: {url}")
        return False

    if not os.path.exists(filepath) or not os.path.isdir(filepath):
        os.makedirs(filepath)

    fullpath = os.path.join(filepath, filename)
    if os.path.exists(fullpath) and os.path.isfile(fullpath):
        os.remove(fullpath)

    # download target file from github release to fullpath
    try:
        urllib.request.urlretrieve(url=url, filename=fullpath)
    except Exception:
        return download(url, filepath, filename, retry - 1)

    logger.info(f"download file {filename} to {fullpath} success")
    return True


def load_mmdb(
    directory: str, repo: str = "Loyalsoldier/geoip", filename: str = "Country.mmdb", update: bool = False
) -> database.Reader:
    filepath = os.path.join(directory, filename)
    if update or not os.path.exists(filepath) or not os.path.isfile(filepath):
        if not download_mmdb(repo, filename, directory):
            return None

    return database.Reader(filepath)


def rename(proxy: dict, reader: database.Reader) -> dict:
    if not proxy or not isinstance(proxy, dict):
        return None

    address = utils.trim(proxy.get("server", ""))
    if not address:
        logger.warning(f"server is empty, proxy: {proxy}")
        return proxy

    try:
        if reader is None:
            logger.error("MMDB reader is None, cannot query geolocation")
            return proxy

        ip = socket.gethostbyname(address)

        # fake ip
        if ip.startswith("198.18.0."):
            logger.warning("cannot get geolocation and rename because IP address is faked")
            return proxy

        response = reader.country(ip)

        # Try to get country name in Chinese
        country = response.country.names.get("zh-CN", "")

        # If Chinese name is not available, try to convert ISO code to Chinese name
        if not country and response.country.iso_code:
            iso_code = response.country.iso_code
            # Try to get Chinese name from ISO code mapping
            country = ISO_TO_CHINESE.get(iso_code, iso_code)

        # Special handling for well-known IPs
        if not country:
            if ip == "1.1.1.1" or ip == "1.0.0.1":
                country = "Cloudflare"
            elif ip.startswith("8.8.8.") or ip.startswith("8.8.4."):
                country = "Google"

        if country:
            proxy["name"] = country
        else:
            logger.warning(f"cannot get geolocation and rename, address: {address}")
    except Exception as e:
        logger.error(f"query ip geolocation failed, address: {address}, error: {str(e)}")

    return proxy


def regularize(
    proxies: list[dict],
    directory: str = "",
    update: bool = False,
    num_threads: int = 0,
    show_progress: bool = True,
    locate: bool = False,
    digits: int = 2,
) -> list[dict]:
    if not proxies or not isinstance(proxies, list):
        return proxies

    if locate:
        directory = utils.trim(directory)
        if not directory:
            directory = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "data")

        repo, filename = "Loyalsoldier/geoip", "Country.mmdb"

        # load mmdb
        reader = load_mmdb(repo=repo, directory=directory, filename=filename, update=update)
        if reader:
            tasks = [[p, reader] for p in proxies if p and isinstance(p, dict)]
            proxies = utils.multi_thread_run(rename, tasks, num_threads, show_progress, "")
        else:
            logger.error(f"skip rename proxies due to cannot load mmdb: {filename}")

    records = defaultdict(list)
    for proxy in proxies:
        name = re.sub(r"-?(\d+|(\d+|\s+|(\d+)?-\d+)[A-Z])$", "", proxy.get("name", "")).strip()
        if not name:
            name = "未知地域"

        proxy["name"] = name
        records[name].append(proxy)

    results = list()
    for name, nodes in records.items():
        if not nodes:
            continue

        n = max(digits, math.floor(math.log10(len(nodes))) + 1)
        for index, node in enumerate(nodes):
            node["name"] = f"{name} {str(index+1).zfill(n)}"
            results.append(node)

    # shuffle
    for _ in range(3):
        random.shuffle(results)

    return results
