#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2025-06-18

"""
SOCKS5/HTTP 代理批量检测工具
支持自定义代理格式解析和并发测试
"""

import argparse
import asyncio
import ipaddress
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import aiohttp
from aiohttp_socks import ProxyConnector

COUNTRY_NAME_ZH = {
    "AD": "安道尔",
    "AE": "阿联酋",
    "AF": "阿富汗",
    "AG": "安提瓜和巴布达",
    "AI": "安圭拉",
    "AL": "阿尔巴尼亚",
    "AM": "亚美尼亚",
    "AO": "安哥拉",
    "AQ": "南极洲",
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
    "BQ": "荷兰加勒比",
    "BR": "巴西",
    "BS": "巴哈马",
    "BT": "不丹",
    "BV": "布韦岛",
    "BW": "博茨瓦纳",
    "BY": "白俄罗斯",
    "BZ": "伯利兹",
    "CA": "加拿大",
    "CC": "科科斯（基林）群岛",
    "CD": "刚果（金）",
    "CF": "中非",
    "CG": "刚果（布）",
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


@dataclass
class ProxyInfo:
    protocol: str
    username: str
    password: str
    host: str
    port: int
    original: str
    remark: str = ""


@dataclass
class TestResult(ProxyInfo):
    proxy: str = ""
    status: str = "failed"
    response_time: Optional[float] = None
    ip: Optional[str] = None
    error: Optional[str] = None

    @classmethod
    def from_proxy(cls, proxy_info: ProxyInfo) -> "TestResult":
        return cls(
            protocol=proxy_info.protocol,
            username=proxy_info.username,
            password=proxy_info.password,
            host=proxy_info.host,
            port=proxy_info.port,
            original=proxy_info.original,
            remark=proxy_info.remark,
            proxy=proxy_info.original,
        )


class ProxyChecker:
    def __init__(
        self,
        timeout: int = 10,
        format_pattern: Optional[str] = None,
        default_port: int = 1080,
        include_asn_name: bool = False,
    ):
        """
        初始化代理检测器

        Args:
            timeout: 超时时间（秒）
            format_pattern: 自定义代理格式模式
            default_port: 默认端口（1-65535），当代理字符串不含端口时使用
        """
        if not (1 <= default_port <= 65535):
            raise ValueError("default_port 必须在 1-65535 之间")

        self.timeout = timeout
        self.format_pattern = format_pattern
        self.default_port = default_port
        self.include_asn_name = include_asn_name
        self.results: List[TestResult] = []
        self.summary: Optional[Dict[str, float]] = None

    def parse_proxy(self, text: str, format_pattern: Optional[str] = None) -> Optional[ProxyInfo]:
        """
        解析代理字符串，支持自定义格式

        支持的格式占位符:
        - {protocol}: 协议类型 (socks5/socks4/http等)
        - {username}: 用户名
        - {password}: 密码
        - {host}: 主机地址
        - {port}: 端口号
        - {remark}: 节点名称（如果代理字符串包含 '#'，则 remark 为 '#' 之后的内容）

        预设格式:
        - None (默认): protocol://username:password@host:port 或 protocol://host:port
        - "username:password:host:port": 用冒号分隔
        - "host:port:username:password": 主机端口在前
        - 自定义格式字符串

        Args:
            text: 代理字符串
            format_pattern: 格式模式字符串

        Returns:
            包含代理信息的字典或None
        """
        text = text.strip()

        if not text or text.startswith("#"):
            return None

        try:
            # 先拆分 remark
            prefix, remark = self._split_remark(text)

            # 如果指定了自定义格式
            if format_pattern:
                info = self._parse_custom_format(prefix, format_pattern)
                if info is not None:
                    info.remark = remark
                return info

            # 默认格式解析 (标准URL格式)
            # 如果不包含协议头，默认添加 socks5://
            if not prefix.startswith(("socks5://", "socks4://", "http://", "https://")):
                prefix = f"socks5://{prefix}"

            result = urlparse(prefix)

            protocol = result.scheme or "socks5"
            if protocol == "https":
                protocol = "http"

            return ProxyInfo(
                protocol=protocol,
                username=result.username or "",
                password=result.password or "",
                host=result.hostname,
                port=result.port or self.default_port,
                original=text,
                remark=remark,
            )
        except Exception as e:
            print(f"解析代理失败: {text} - {e}")
            return None

    # 新增：拆分主体与 remark 的复用方法
    def _split_remark(self, text: str) -> tuple[str, str]:
        """
        将代理字符串按第一个 '#' 分割为主体和 remark。
        如果字符串以 '#' 开头或不包含 '#'，返回原字符串和空 remark。
        """
        if not text:
            return text, ""
        if text.startswith("#") or "#" not in text:
            return text, ""

        prefix, remark = text.split("#", 1)
        return prefix.strip(), remark.strip()

    def _parse_custom_format(self, text: str, format_pattern: str) -> Optional[ProxyInfo]:
        """
        按自定义格式解析代理字符串

        Args:
            text: 代理字符串, 不含 remark
            format_pattern: 格式模式，如 "{protocol}://{username}:{password}:{host}:{port}"

        Returns:
            包含代理信息的字典或None, 结果中包含 remark 字段
        """
        # 先拆分主体与 remark，以保证兼容直接调用该方法的场景
        prefix, remark = self._split_remark(text)

        # 提取格式中的占位符
        placeholders = re.findall(r"\{(\w+)\}", format_pattern)

        # 将格式模式转换为正则表达式
        regex_pattern = format_pattern
        for placeholder in placeholders:
            # 根据占位符类型设置不同的匹配规则
            if placeholder == "port":
                regex_pattern = regex_pattern.replace(f"{{{placeholder}}}", r"(?P<" + placeholder + r">\d+)")
            elif placeholder == "protocol":
                regex_pattern = regex_pattern.replace(f"{{{placeholder}}}", r"(?P<" + placeholder + r">\w+)")
            else:
                regex_pattern = regex_pattern.replace(f"{{{placeholder}}}", r"(?P<" + placeholder + r">[^:@/\s]+)")

        # 转义特殊字符
        regex_pattern = regex_pattern.replace("://", r"://")

        # 匹配代理字符串
        match = re.match(regex_pattern, prefix)

        if not match:
            print(f"代理格式不匹配: {text}")
            return None

        # 提取匹配的值
        protocol = "socks5"
        username = ""
        password = ""
        host = ""
        port = self.default_port

        for placeholder in placeholders:
            value = match.group(placeholder)
            if placeholder == "port":
                port = int(value)
            elif placeholder == "protocol":
                protocol = value
            elif placeholder == "username":
                username = value
            elif placeholder == "password":
                password = value
            elif placeholder == "host":
                host = value

        if protocol == "https":
            protocol = "http"

        return ProxyInfo(
            protocol=protocol,
            username=username,
            password=password,
            host=host,
            port=port,
            original=text,
            remark=remark,
        )

    async def test_proxy(self, proxy_info: ProxyInfo, retries: int = 3) -> TestResult:
        """
        Test a single proxy with retries.
        """
        result = TestResult.from_proxy(proxy_info)

        # Build proxy URL
        if proxy_info.username and proxy_info.password:
            proxy_url = (
                f"{proxy_info.protocol}://{proxy_info.username}:{proxy_info.password}"
                f"@{proxy_info.host}:{proxy_info.port}"
            )
        else:
            proxy_url = f"{proxy_info.protocol}://{proxy_info.host}:{proxy_info.port}"

        start_time = datetime.now()
        try:
            connector = ProxyConnector.from_url(proxy_url)
            async with aiohttp.ClientSession(connector=connector) as session:
                ip_address = await self._resolve_ip_with_proxy(session, proxy_info.host, retries)
                if not ip_address:
                    result.error = "Failed to get IP from ipinfo.io/ip"
                    return result

                ip_data, ip_error = await self._fetch_ipinfo(session, ip_address, retries)
                if not ip_data:
                    result.error = ip_error or "Failed to get IP info from ipinfo.io"
                    return result

                remark = self._build_remark_from_ipinfo(ip_data)
                result.remark = remark
                result.ip = ip_address
                result.status = "success"
                result.response_time = round((datetime.now() - start_time).total_seconds(), 2)
                result.error = None
                result.proxy = self._format_standard(proxy_info, remark)
                proxy_info.remark = remark

                return result
        except asyncio.TimeoutError:
            result.error = "Timeout"
            return result
        except Exception as e:
            result.error = str(e)[:100]
            return result

    def _is_ipv4(self, host: str) -> bool:
        if not host:
            return False
        try:
            return isinstance(ipaddress.ip_address(host), ipaddress.IPv4Address)
        except ValueError:
            return False

    async def _resolve_ip_with_proxy(self, session: aiohttp.ClientSession, host: str, retries: int) -> Optional[str]:
        if self._is_ipv4(host):
            return host

        url = "https://ipinfo.io/ip"
        for attempt in range(1, retries + 1):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.timeout)) as response:
                    if response.status == 200:
                        text = (await response.text()).strip()
                        try:
                            ipaddress.ip_address(text)
                            return text
                        except ValueError:
                            pass
            except asyncio.TimeoutError:
                pass
            except Exception:
                pass

            if attempt < retries:
                await asyncio.sleep(attempt)

        return None

    async def _fetch_ipinfo(
        self, session: aiohttp.ClientSession, ip_address: str, retries: int
    ) -> Tuple[Optional[Dict], Optional[str]]:
        url = f"https://ipinfo.io/widget/demo/{ip_address}"
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.timeout)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, dict):
                            return data.get("data", data), None
                        last_error = "Invalid JSON response"
                    else:
                        last_error = f"HTTP {response.status}"
            except asyncio.TimeoutError:
                last_error = "Timeout"
            except Exception as e:
                last_error = str(e)[:100]

            if attempt < retries:
                await asyncio.sleep(attempt)

        return None, last_error

    def _country_flag_emoji(self, country_code: str) -> str:
        if not country_code or len(country_code) != 2:
            return ""
        code = country_code.upper()
        if not code.isalpha():
            return ""
        return chr(0x1F1E6 + ord(code[0]) - ord("A")) + chr(0x1F1E6 + ord(code[1]) - ord("A"))

    def _country_name_zh(self, country_code: str) -> str:
        if not country_code:
            return ""
        return COUNTRY_NAME_ZH.get(country_code.upper(), "")

    def _format_standard(self, proxy_info: ProxyInfo, remark: str) -> str:
        auth = ""
        if proxy_info.username or proxy_info.password:
            auth = f"{proxy_info.username}:{proxy_info.password}@"
        base = f"{proxy_info.protocol}://{auth}{proxy_info.host}:{proxy_info.port}"
        if remark:
            return f"{base}#{remark}"
        return base

    def _yaml_quote(self, value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _format_yaml_line(self, result: TestResult) -> str:
        name = result.remark or result.host
        parts = [
            f"name: {self._yaml_quote(name)}",
            f"server: {self._yaml_quote(result.host)}",
            f"port: {result.port}",
            f"type: {self._yaml_quote(result.protocol)}",
        ]
        if result.username:
            parts.append(f"username: {self._yaml_quote(result.username)}")
        if result.password:
            parts.append(f"password: {self._yaml_quote(result.password)}")
        return "  - {" + ", ".join(parts) + "}"

    def _build_remark_from_ipinfo(self, ip_data: Dict) -> str:
        country_code = (ip_data.get("country") or "").upper()
        flag = self._country_flag_emoji(country_code)
        country_display = self._country_name_zh(country_code) or "未知"

        asn_info = ip_data.get("asn", {}) or {}
        company_info = ip_data.get("company", {}) or {}
        asn_type = (asn_info.get("type") or "").lower()
        company_type = (company_info.get("type") or "").lower()

        asn_name = (asn_info.get("domain") or "").strip()
        if not asn_name:
            asn_name = (asn_info.get("name") or "").strip()

        if asn_name:
            parts = [p for p in re.split(r"[\s,\.]+", asn_name) if p]
            company_name = parts[0].upper() if parts else "UNKNOWN"
        else:
            company_name = "UNKNOWN"

        if asn_type == "isp" and company_type == "isp":
            label = "家宽"
        elif asn_type == "isp" or company_type == "isp":
            label = "商宽"
        elif asn_type == "edu" or company_type == "edu":
            label = "教育"
        else:
            label = ""

        base = f"{flag} {country_display}{label}".strip()
        if self.include_asn_name and company_name:
            return f"{base} [{company_name}]".strip()
        return base

    def _renumber_output_file(self, output_file: str, output_format: str, digits: int = 2) -> None:
        proxies = read_proxies_from_file(output_file)
        if not proxies:
            return

        proxy_infos: List[ProxyInfo] = []
        for proxy in proxies:
            info = self.parse_proxy(proxy)
            if info:
                proxy_infos.append(info)

        if not proxy_infos:
            return

        groups: Dict[str, List[ProxyInfo]] = {}
        for info in proxy_infos:
            name = (info.remark or "").strip()
            if name:
                name = re.sub(r"\s+\d+$", "", name).strip()
            if not name:
                name = info.host or "UNKNOWN"
            info.remark = name
            groups.setdefault(name, []).append(info)

        lines: List[str] = []
        for name, nodes in groups.items():
            width = max(digits, len(str(len(nodes))))
            for index, info in enumerate(nodes):
                content = f"{name} {str(index + 1).zfill(width)}"
                info.remark = content
                if output_format == "clash":
                    result = TestResult.from_proxy(info)
                    result.remark = content
                    lines.append(self._format_yaml_line(result))
                else:
                    lines.append(self._format_standard(info, content))

        with open(output_file, "w", encoding="utf-8") as f:
            if output_format == "clash":
                f.write("proxies:\n")
            for line in lines:
                f.write(line + "\n")

    async def check_proxies(
        self,
        proxies: List[str],
        max_concurrent: int = 10,
        output_file: Optional[str] = None,
        output_format: str = "v2ray",
    ) -> List[TestResult]:
        """
        并发检测多个代理

        Args:
            proxies: 代理列表
            max_concurrent: 最大并发数
            output_file: 输出文件路径，启用后边测边写
            output_format: 输出格式为 v2ray 或 clash

        Returns:
            检测结果列表
        """
        # 解析代理
        proxy_infos = []
        seen_keys = set()
        for proxy in proxies:
            info = self.parse_proxy(proxy, self.format_pattern)
            if info:
                key = (
                    (info.protocol or "").lower(),
                    (info.host or "").lower(),
                    info.port,
                    info.username or "",
                    info.password or "",
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                proxy_infos.append(info)

        if not proxy_infos:
            print("没有有效的代理需要检测")
            return []

        print(f"开始检测 {len(proxy_infos)} 个代理...")
        print(f"并发数: {max_concurrent}, 超时: {self.timeout}秒")
        print("-" * 80)

        output_format = (output_format or "v2ray").lower()
        write_queue: Optional[asyncio.Queue] = None
        writer_task: Optional[asyncio.Task] = None
        output_handle = None

        if not output_file:
            output_file = f'{output_format}.{"txt" if output_format == "v2ray" else "yaml"}'

        output_handle = open(output_file, "w", encoding="utf-8")
        if output_format == "clash":
            output_handle.write("proxies:\n")
            output_handle.flush()

        write_queue = asyncio.Queue()

        async def writer():
            while True:
                line = await write_queue.get()
                if line is None:
                    break
                output_handle.write(line)
                output_handle.flush()

        writer_task = asyncio.create_task(writer())

        stats = {"total": len(proxy_infos), "success": 0, "failed": 0, "total_time": 0.0}
        stats_lock = asyncio.Lock()

        # 创建信号量控制并发
        semaphore = asyncio.Semaphore(max_concurrent)

        async def test_with_semaphore(proxy_info):
            async with semaphore:
                result = await self.test_proxy(proxy_info)

                # 实时输出结果
                status_icon = "✓" if result.status == "success" else "✗"
                if result.status == "success":
                    print(f"{status_icon} {result.original[:60]}... | {result.response_time}s | IP: {result.ip}")
                    if write_queue:
                        line = self._format_yaml_line(result) if output_format == "clash" else result.proxy
                        await write_queue.put(line + "\n")
                else:
                    print(f"{status_icon} {result.original[:60]}... | {result.error}")

                async with stats_lock:
                    if result.status == "success":
                        stats["success"] += 1
                        if result.response_time is not None:
                            stats["total_time"] += result.response_time
                    else:
                        stats["failed"] += 1

                return result

        # 并发执行测试
        tasks = [test_with_semaphore(info) for info in proxy_infos]
        try:
            if output_file:
                for task in asyncio.as_completed(tasks):
                    await task
                results = []
            else:
                results = await asyncio.gather(*tasks)
        finally:
            if write_queue and writer_task:
                await write_queue.put(None)
                await writer_task
            if output_handle:
                output_handle.close()

        self.summary = {
            "total": stats["total"],
            "success": stats["success"],
            "failed": stats["failed"],
            "avg_time": (stats["total_time"] / stats["success"]) if stats["success"] > 0 else 0.0,
        }

        if output_file and stats["success"] > 0:
            self._renumber_output_file(output_file, output_format)

        if output_file:
            self.results = []
            return []

        self.results = results
        return results

    def print_summary(self):
        """打印检测结果摘要"""
        if self.summary:
            total = int(self.summary["total"])
            success = int(self.summary["success"])
            failed = int(self.summary["failed"])
            avg_time = float(self.summary["avg_time"])
        elif self.results:
            total = len(self.results)
            success = sum(1 for r in self.results if r.status == "success")
            failed = total - success
            avg_time = sum(r.response_time for r in self.results if r.response_time) / success if success > 0 else 0.0
        else:
            return

        print("\n" + "=" * 80)
        print("检测结果摘要:")
        print(f"总计: {total} | 成功: {success} | 失败: {failed}")
        print(f"成功率: {success/total*100:.1f}%")

        if success > 0:
            print(f"平均响应时间: {avg_time:.2f}秒")

        print("=" * 80)

    def save_results(self, output_file: str, output_format: str = "v2ray"):
        """
        保存结果到文件

        Args:
            output_file: 输出文件路径
            output_format: 输出格式为 v2ray 或 clash
        """
        output_format = (output_format or "v2ray").lower()
        results_to_save = [r for r in self.results if r.status == "success"]

        with open(output_file, "w", encoding="utf-8") as f:
            if output_format == "clash":
                f.write("proxies:\n")
                for result in results_to_save:
                    f.write(self._format_yaml_line(result) + "\n")
            else:
                for result in results_to_save:
                    f.write(result.proxy + "\n")

        print(f"\n结果已保存到: {output_file}")


def read_proxies_from_file(file_path: str) -> List[str]:
    """
    从文件读取代理列表

    Args:
        file_path: 文件路径

    Returns:
        代理列表
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        def strip_quotes(value: str) -> str:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                return value[1:-1]
            return value

        def split_inline_items(text: str) -> List[str]:
            buffers, items = [], []
            in_quote = None
            escape = False

            for c in text:
                if in_quote:
                    if escape:
                        buffers.append(c)
                        escape = False
                        continue
                    if c == "\\":
                        escape = True
                        buffers.append(c)
                        continue
                    if c == in_quote:
                        in_quote = None
                    buffers.append(c)
                    continue
                if c in ("'", '"'):
                    in_quote = c
                    buffers.append(c)
                    continue
                if c == ",":
                    item = "".join(buffers).strip()
                    if item:
                        items.append(item)
                    buffers = []
                    continue
                buffers.append(c)

            tail = "".join(buffers).strip()
            if tail:
                items.append(tail)
            return items

        def parse_inline_map(text: str) -> Dict[str, str]:
            data: Dict[str, str] = {}
            for item in split_inline_items(text):
                if ":" not in item:
                    continue
                key, value = item.split(":", 1)
                data[key.strip()] = strip_quotes(value.strip())
            return data

        def parse_yaml_entries(file_lines: List[str]) -> List[Dict[str, str]]:
            entries: List[Dict[str, str]] = []
            in_proxies = False
            current: Optional[Dict[str, str]] = None
            for raw in file_lines:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("proxies:"):
                    in_proxies = True
                    continue
                if not in_proxies:
                    continue
                if line.startswith("- "):
                    if current:
                        entries.append(current)
                        current = None
                    rest = line[2:].strip()
                    if rest.startswith("{") and rest.endswith("}"):
                        entries.append(parse_inline_map(rest[1:-1]))
                    else:
                        current = {}
                        if ":" in rest:
                            key, value = rest.split(":", 1)
                            current[key.strip()] = strip_quotes(value.strip())
                else:
                    if current and ":" in line:
                        key, value = line.split(":", 1)
                        current[key.strip()] = strip_quotes(value.strip())
            if current:
                entries.append(current)
            return entries

        def yaml_entries_to_proxies(entries: List[Dict[str, str]]) -> List[str]:
            proxies: List[str] = []
            for entry in entries:
                host = entry.get("server") or entry.get("host")
                port_value = entry.get("port")
                if not host or port_value is None:
                    continue
                try:
                    port = int(str(port_value))
                except ValueError:
                    continue
                protocol = (entry.get("type") or "socks5").strip()
                if protocol == "https":
                    protocol = "http"
                username = entry.get("username") or ""
                password = entry.get("password") or ""
                name = entry.get("name") or ""
                auth = ""
                if username or password:
                    auth = f"{username}:{password}@"
                proxy = f"{protocol}://{auth}{host}:{port}"
                if name:
                    proxy = f"{proxy}#{name}"
                proxies.append(proxy)
            return proxies

        if any(line.strip().startswith("proxies:") for line in lines):
            entries = parse_yaml_entries(lines)
            clash_proxies = yaml_entries_to_proxies(entries)
            if clash_proxies:
                return clash_proxies

        proxies = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
        return proxies
    except FileNotFoundError:
        print(f"错误: 文件不存在 - {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"错误: 读取文件失败 - {e}")
        sys.exit(1)


def valid_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("端口必须为整数")
    if port < 1 or port > 65535:
        raise argparse.ArgumentTypeError("端口必须在 1-65535 之间")
    return port


def _asyncio_exception_handler(loop: asyncio.AbstractEventLoop, context: Dict):
    exc = context.get("exception")
    message = context.get("message", "")
    if isinstance(exc, ConnectionResetError):
        return
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 10054:
        return
    if "ProactorBasePipeTransport._call_connection_lost" in message:
        return
    loop.default_exception_handler(context)


async def main():
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_asyncio_exception_handler)

    parser = argparse.ArgumentParser(
        description="SOCKS5/HTTP代理批量检测工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 标准格式检测
  %(prog)s -f proxies.txt
  
  # 自定义并发和超时
  %(prog)s -f proxies.txt -c 20 -t 15
  
  # 单个代理测试
  %(prog)s -p "socks5://user:pass@host:port"
  
  # 自定义格式示例
  %(prog)s -f proxies.txt --input-format "{protocol}://{username}:{password}:{host}:{port}"
  %(prog)s -f proxies.txt --input-format "{host}:{port}:{username}:{password}"
  %(prog)s -f proxies.txt --input-format "{username}:{password}:{host}:{port}"
  %(prog)s -f proxies.txt --input-format "socks5://{host}:{port}:{username}:{password}"

支持的格式占位符:
  {protocol}  - 协议类型 (socks5/socks4/http等)
  {username}  - 用户名
  {password}  - 密码
  {host}      - 主机地址/IP
  {port}      - 端口号
        """,
    )

    parser.add_argument("-f", "--file", help="包含代理列表的文件路径")
    parser.add_argument("-p", "--proxy", help="单个代理字符串")
    parser.add_argument("-c", "--concurrent", type=int, default=10, help="最大并发数 (默认: 10)")
    parser.add_argument("-t", "--timeout", type=int, default=10, help="超时时间/秒 (默认: 10)")
    parser.add_argument("-o", "--output", help="输出文件路径")
    parser.add_argument(
        "--output-format",
        choices=["v2ray", "clash"],
        default="v2ray",
        help="输出格式: v2ray 或 clash (默认: v2ray)",
    )
    parser.add_argument(
        "--input-format",
        dest="format_pattern",
        help='输入代理格式，如: "{protocol}://{username}:{password}:{host}:{port}"',
    )
    parser.add_argument(
        "--default-port", dest="default_port", type=valid_port, default=1080, help="默认端口 (1-65535，默认: 1080)"
    )
    parser.add_argument(
        "--asn-name",
        dest="include_asn_name",
        action="store_true",
        help="在备注中追加 ASN 名称 (默认不追加)",
    )

    args = parser.parse_args()

    # 获取代理列表
    proxies = []
    if args.file:
        proxies = read_proxies_from_file(args.file)
    elif args.proxy:
        proxies = [args.proxy]
    else:
        parser.print_help()
        sys.exit(1)

    if not proxies:
        print("错误: 没有找到任何代理")
        sys.exit(1)

    # 显示格式信息
    if args.format_pattern:
        print(f"使用自定义格式: {args.format_pattern}")
        print("-" * 80)

    # 创建检测器并执行检测
    checker = ProxyChecker(
        timeout=args.timeout,
        format_pattern=args.format_pattern,
        default_port=args.default_port,
        include_asn_name=args.include_asn_name,
    )

    await checker.check_proxies(
        proxies,
        max_concurrent=args.concurrent,
        output_file=args.output,
        output_format=args.output_format,
    )

    # 打印摘要
    checker.print_summary()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n检测已取消")
        sys.exit(0)
