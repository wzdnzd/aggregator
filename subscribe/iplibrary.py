# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2026-09-07

import html
import ipaddress
import json
import random
import re
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional

RequestFn = Callable[..., tuple[bool, Any]]

import utils
from logger import logger

# HTTPS only. Fetched via CONNECT + TLS through the HTTP inbound.
EGRESS_IPV4_URLS = (
    "https://ipinfo.io/ip",
    "https://api-ipv4.ip.sb/ip",
    "https://ipv4.ip.sb/ip",
    "https://ipv4.icanhazip.com",
    "https://icanhazip.com",
    "https://api4.ipify.org",
    "https://api.ipify.org",
    "https://v4.ident.me",
    "https://ident.me",
    "https://iplark.com/ipapi/public/ip",
    "https://ipv4.wtfismyip.com/text",
    "https://ifconfig.me/ip",
    "https://ifconfig.co/ip",
    "https://ifconfig.io/ip",
    "https://ipecho.net/plain",
    "https://wgetip.com",
    "https://myexternalip.com/raw",
    "https://ip.tyk.nu",
    "https://eth0.me",
    "https://ipapi.co/ip",
    "https://ipv4.nsupdate.info/myip",
    "https://myip.ipip.net",
    "https://v4.ip.zxinc.org/getip",
    "https://www.cloudflare.com/cdn-cgi/trace",
    "https://1.1.1.1/cdn-cgi/trace",
    "https://httpbin.org/ip",
    "https://jsonip.com",
    "https://ipv4.seeip.org",
    "https://l2.io/ip",
)
_EGRESS_IPV4_TRIES = 8
_IPV4_RE = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}")
ECHO_HEADERS = {
    "Accept": "text/plain, application/json, */*",
    "Accept-Language": "en-US,en;q=0.8,zh-CN;q=0.6",
    "Cache-Control": "no-cache",
    "Origin": None,
    "Referer": None,
}


def _valid_public_ipv4(text: str) -> str:
    try:
        addr = ipaddress.ip_address(utils.trim(text))
    except ValueError:
        return ""
    if addr.version != 4 or not addr.is_global:
        return ""
    return str(addr)


def _parse_egress_ipv4(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, dict):
        chunks = []
        for key in ("ip", "origin", "query", "address", "IPv4", "ipv4"):
            value = content.get(key)
            if value is not None:
                chunks.append(str(value))
        content = "\n".join(chunks) if chunks else json.dumps(content, ensure_ascii=False)
    elif not isinstance(content, str):
        content = str(content)

    text = utils.trim(content)
    if not text:
        return ""
    if text[0] in "{[":
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            ip = _parse_egress_ipv4(parsed)
            if ip:
                return ip

    # Cloudflare trace lists h=1.1.1.1 before ip=; prefer the ip field
    for match in re.finditer(r"(?im)^ip=([0-9.]+)\s*$", text):
        ip = _valid_public_ipv4(match.group(1))
        if ip:
            return ip

    for match in _IPV4_RE.finditer(text):
        ip = _valid_public_ipv4(match.group(0))
        if ip:
            return ip
    return ""


def resolve_egress_ipv4(port: int, request: RequestFn, max_retries: int = 2, timeout: int = 15) -> str:
    urls = list(EGRESS_IPV4_URLS)
    random.shuffle(urls)
    tries = min(len(urls), max(_EGRESS_IPV4_TRIES, max_retries + 1))
    for url in urls[:tries]:
        success, content = request(
            port=port,
            url=url,
            max_retries=1,
            timeout=timeout,
            headers=ECHO_HEADERS,
            deserialize=False,
            quiet=True,
        )
        ip = _parse_egress_ipv4(content) if success else ""
        if ip:
            return ip

    return ""


@dataclass
class IPClassifyResult:
    country_code: str = ""
    company_type: str = ""
    asn_type: str = ""
    score: Optional[int] = None
    raw: dict[str, object] = field(default_factory=dict)


class IPLibrary:
    name: str = ""
    needs_egress_ip: bool = False

    def fetch(
        self, port: int, request: RequestFn, max_retries: int = 2, timeout: int = 12, ip: str = ""
    ) -> dict[str, object]:
        raise NotImplementedError

    def classify(self, data: dict[str, object]) -> IPClassifyResult:
        raise NotImplementedError

    def _resolve_egress_ip(
        self, port: int, request: RequestFn, max_retries: int = 2, timeout: int = 15, ip: str = ""
    ) -> str:
        text = _valid_public_ipv4(ip) if ip else ""
        if text:
            return text
        return resolve_egress_ipv4(port, request, max_retries=max_retries, timeout=timeout)

    def _get(
        self,
        request: RequestFn,
        port: int,
        url: str,
        max_retries: int,
        timeout: int,
        headers: dict[str, str] | None = None,
        deserialize: bool = True,
    ) -> object | None:
        success, response = request(
            port=port,
            url=url,
            max_retries=max_retries,
            timeout=timeout,
            headers=headers,
            deserialize=deserialize,
        )
        if not success:
            return None
        return response

    @staticmethod
    def _parse_trust_score(value: object, *, invert: bool = False) -> Optional[int]:
        if value is None:
            return None

        try:
            n = int(value)
        except (TypeError, ValueError):
            try:
                n = int(float(value))
            except (TypeError, ValueError):
                return None

        if invert:
            n = 100 - n

        return max(0, min(100, n))

    @staticmethod
    def _nested(data: object, *keys: str) -> dict[str, object]:
        current = data
        for key in keys:
            if not isinstance(current, dict):
                return {}
            current = current.get(key)
        return current if isinstance(current, dict) else {}


class IPNetCoffeeLibrary(IPLibrary):
    name = "ipnetcoffee"
    needs_egress_ip = True

    def fetch(
        self, port: int, request: RequestFn, max_retries: int = 2, timeout: int = 12, ip: str = ""
    ) -> dict[str, object]:
        ip = self._resolve_egress_ip(port, request, max_retries=max_retries, timeout=timeout, ip=ip)
        if not ip:
            return {}

        url = f"https://ip.net.coffee/api/ip/lookup/{urllib.parse.quote(ip, safe='')}"
        response = self._get(request, port, url, max_retries, timeout)
        return response if isinstance(response, dict) else {}

    def classify(self, data: dict[str, object]) -> IPClassifyResult:
        data = data if isinstance(data, dict) else {}
        if data.get("isResidential") is True and utils.trim(data.get("company_type", "")) != "business":
            company_type, asn_type = "isp", "isp"
        else:
            company_type, asn_type = "hosting", "hosting"

        return IPClassifyResult(
            country_code=utils.trim(data.get("countryCode", "")).upper(),
            company_type=company_type,
            asn_type=asn_type,
            score=self._parse_trust_score(data.get("trust_score")),
            raw=data,
        )


class MeowVPSLibrary(IPLibrary):
    name = "meowvps"
    needs_egress_ip = True

    def fetch(
        self, port: int, request: RequestFn, max_retries: int = 2, timeout: int = 12, ip: str = ""
    ) -> dict[str, object]:
        ip = self._resolve_egress_ip(port, request, max_retries=max_retries, timeout=timeout, ip=ip)
        if not ip:
            return {}

        url = f"https://meowvps.com/api/ip-aggregator/{urllib.parse.quote(ip, safe='')}"
        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.8",
            "Origin": "https://meowvps.com",
            "Referer": "https://meowvps.com/tools/ip-check/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0.0.0 Safari/537.36"
            ),
        }
        response = self._get(request, port, url, max_retries, timeout, headers=headers)
        if not isinstance(response, dict):
            return {}
        if response.get("success") is False:
            logger.warning(f"MeowVPS lookup failed, ip: {ip}")
            return {}

        return response

    def classify(self, data: dict[str, object]) -> IPClassifyResult:
        data = data if isinstance(data, dict) else {}
        core = self._nested(data, "core_data")
        digital = self._nested(data, "api4", "digital")
        traits = self._nested(data, "minfraud", "traits")
        scores = self._nested(data, "risk_assessment", "ipdata", "scores")

        digital_type = "" if digital.get("type") is None else str(digital.get("type")).strip().lower()
        user_type = str(traits.get("user_type") or "").strip().lower()

        if digital_type == "edu" or user_type in {"college", "education", "edu"}:
            company_type, asn_type = "edu", "edu"
        elif self._is_residential(digital_type, user_type, data):
            company_type, asn_type = "isp", "isp"
        else:
            company_type, asn_type = "hosting", "hosting"

        country_code = utils.trim(core.get("country_code") or digital.get("country_code") or "").upper()
        return IPClassifyResult(
            country_code=country_code,
            company_type=company_type,
            asn_type=asn_type,
            score=self._parse_trust_score(scores.get("trust_score")),
            raw=data,
        )

    @classmethod
    def _is_residential(cls, digital_type: str, user_type: str, data: dict[str, object]) -> bool:
        if digital_type in {"hosting", "edu"}:
            return False
        if user_type in {"hosting", "content_delivery_network", "college"}:
            return False
        if user_type in {"residential", "traveler", "cellular"}:
            return True
        if digital_type:
            return False

        ipapi = cls._nested(data, "risk_assessment", "ipapi")
        threat = cls._nested(data, "risk_assessment", "ipdata", "threat")
        if ipapi.get("hosting") is True or threat.get("is_datacenter") is True:
            return False

        return True


class IPPureLibrary(IPLibrary):
    name = "ippure"

    def fetch(
        self, port: int, request: RequestFn, max_retries: int = 2, timeout: int = 12, ip: str = ""
    ) -> dict[str, object]:
        response = self._get(request, port, "https://my.ippure.com/v1/info", max_retries, timeout)
        return response if isinstance(response, dict) else {}

    def classify(self, data: dict[str, object]) -> IPClassifyResult:
        data = data if isinstance(data, dict) else {}
        if data.get("isResidential", False):
            company_type, asn_type = "isp", "isp"
        else:
            company_type, asn_type = "hosting", "hosting"

        return IPClassifyResult(
            country_code=utils.trim(data.get("countryCode", "")).upper(),
            company_type=company_type,
            asn_type=asn_type,
            score=self._parse_trust_score(data.get("fraudScore"), invert=True),
            raw=data,
        )


class IP2LocationLibrary(IPLibrary):
    name = "ip2location"

    def fetch(
        self, port: int, request: RequestFn, max_retries: int = 2, timeout: int = 12, ip: str = ""
    ) -> dict[str, object]:
        headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
        response = self._get(
            request,
            port,
            "https://www.ip2location.com/demo",
            max_retries,
            timeout,
            headers=headers,
            deserialize=False,
        )
        if not isinstance(response, str):
            return {}

        data = self._extract_data(response)
        if not data:
            logger.warning("Failed to extract JSON payload from ip2location demo HTML")
            return {}
        return data

    def classify(self, data: dict[str, object]) -> IPClassifyResult:
        data = data if isinstance(data, dict) else {}
        usage_type = utils.trim(data.get("usage_type", "")).lower()
        as_info = data.get("as_info", {})
        if not isinstance(as_info, dict):
            as_info = {}
        as_usage_type = utils.trim(as_info.get("as_usage_type", "")).lower()

        check = lambda usage: usage.startswith("isp") or usage == "mob"
        if check(usage_type) and check(as_usage_type):
            company_type, asn_type = "isp", "isp"
        else:
            company_type, asn_type = "hosting", "hosting"

        return IPClassifyResult(
            country_code=utils.trim(data.get("country_code", "")).upper(),
            company_type=company_type,
            asn_type=asn_type,
            score=self._parse_trust_score(data.get("fraud_score"), invert=True),
            raw=data,
        )

    @staticmethod
    def _extract_data(content: str) -> dict[str, object]:
        if not content or not isinstance(content, str):
            return {}

        pattern = r'<code\b[^>]*class=["\'][^"\']*\blanguage-json\b[^"\']*["\'][^>]*>(.*?)</code>\s*</pre>'
        groups = re.findall(pattern, content, flags=re.I | re.S)
        if not groups:
            return {}

        for group in groups:
            payload = utils.trim(group)
            if not payload:
                continue

            payload = re.sub(r"<[^>]+>", "", payload, flags=re.I | re.S)
            payload = html.unescape(payload)

            try:
                data = json.loads(payload)
            except Exception:
                continue

            if isinstance(data, dict) and data:
                return data

        return {}


class IPLarkLibrary(IPLibrary):
    name = "iplark"

    def fetch(
        self, port: int, request: RequestFn, max_retries: int = 2, timeout: int = 12, ip: str = ""
    ) -> dict[str, object]:
        response = self._get(request, port, "https://iplark.com/ipapi/public/ipinfo", max_retries, timeout)
        return response if isinstance(response, dict) else {}

    def classify(self, data: dict[str, object]) -> IPClassifyResult:
        data = data if isinstance(data, dict) else {}
        node_type = utils.trim(data.get("type", "")).lower()
        if node_type == "isp":
            company_type, asn_type = "isp", "isp"
        elif node_type == "business":
            company_type, asn_type = "business", "business"
        else:
            company_type, asn_type = "hosting", "hosting"

        return IPClassifyResult(
            country_code=utils.trim(data.get("country_code", "")).upper(),
            company_type=company_type,
            asn_type=asn_type,
            raw=data,
        )


class IPInfoLibrary(IPLibrary):
    name = "ipinfo"
    needs_egress_ip = True

    def fetch(
        self, port: int, request: RequestFn, max_retries: int = 2, timeout: int = 12, ip: str = ""
    ) -> dict[str, object]:
        ip = self._resolve_egress_ip(port, request, max_retries=max_retries, timeout=timeout, ip=ip)
        if not ip:
            return {}

        url = f"https://ipinfo.io/widget/demo/{ip}"
        response = self._get(request, port, url, max_retries, timeout)
        if not isinstance(response, dict):
            return {}

        data = response.get("data", response)
        return data if isinstance(data, dict) else {}

    def classify(self, data: dict[str, object]) -> IPClassifyResult:
        data = data if isinstance(data, dict) else {}
        company = data.get("company", {}) if isinstance(data.get("company"), dict) else {}
        asn = data.get("asn", {}) if isinstance(data.get("asn"), dict) else {}
        return IPClassifyResult(
            country_code=utils.trim(data.get("country", "")).upper(),
            company_type=utils.trim(company.get("type", "")).lower(),
            asn_type=utils.trim(asn.get("type", "")).lower(),
            raw=data,
        )


class IPApiLibrary(IPLibrary):
    name = "ipapi"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = utils.trim(api_key)

    def fetch(
        self, port: int, request: RequestFn, max_retries: int = 2, timeout: int = 12, ip: str = ""
    ) -> dict[str, object]:
        url = "https://api.ipapi.is"
        if self.api_key:
            url += f"?key={self.api_key}"

        response = self._get(request, port, url, max_retries, timeout)
        return response if isinstance(response, dict) else {}

    def classify(self, data: dict[str, object]) -> IPClassifyResult:
        data = data if isinstance(data, dict) else {}
        location = data.get("location", {}) if isinstance(data.get("location"), dict) else {}
        company = data.get("company", {}) if isinstance(data.get("company"), dict) else {}
        asn = data.get("asn", {}) if isinstance(data.get("asn"), dict) else {}
        return IPClassifyResult(
            country_code=utils.trim(location.get("country_code", "")).upper(),
            company_type=utils.trim(company.get("type", "")).lower(),
            asn_type=utils.trim(asn.get("type", "")).lower(),
            raw=data,
        )


PROVIDERS_ORDER = ["ipnetcoffee", "meowvps", "ippure", "ip2location", "ipinfo"]

LIBRARIES = {
    "ipnetcoffee": IPNetCoffeeLibrary,
    "meowvps": MeowVPSLibrary,
    "ippure": IPPureLibrary,
    "ip2location": IP2LocationLibrary,
    "iplark": IPLarkLibrary,
    "ipinfo": IPInfoLibrary,
    "ipapi": IPApiLibrary,
}


def get_providers(preferred: str) -> list[str]:
    library = utils.trim(preferred).lower()
    if library not in PROVIDERS_ORDER:
        if library != "":
            logger.warning(f"IP library {library} is not be supported")

        library = "ipnetcoffee"

    return [library] + [item for item in PROVIDERS_ORDER if item != library]


def create_library(name: str, api_key: str = "") -> IPLibrary:
    key = utils.trim(name).lower()
    if key not in LIBRARIES:
        key = "ipnetcoffee"

    cls = LIBRARIES[key]
    if cls is IPApiLibrary:
        return IPApiLibrary(api_key=api_key)

    return cls()
