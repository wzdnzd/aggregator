# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2023-05-25

import re
import urllib

import utils

OPTIONS_HEADERS = {
    "Accept": "*/*",
    "Access-Control-Request-Headers": "authorization,content-type",
    "Access-Control-Request-Method": "POST",
    "Origin": "https://platform.openai.com",
    "Sec-Fetch-Mode": "cors",
    "User-Agent": utils.USER_AGENT,
}

ALLOWED_COUNTRY_CODES = set(
    [
        "AL",
        "DZ",
        "AD",
        "AO",
        "AG",
        "AR",
        "AM",
        "AU",
        "AT",
        "AZ",
        "BS",
        "BD",
        "BB",
        "BE",
        "BZ",
        "BJ",
        "BT",
        "BO",
        "BA",
        "BW",
        "BR",
        "BN",
        "BG",
        "BF",
        "CV",
        "CA",
        "CL",
        "CO",
        "KM",
        "CG",
        "CR",
        "CI",
        "HR",
        "CY",
        "CZ",
        "DK",
        "DJ",
        "DM",
        "DO",
        "EC",
        "SV",
        "EE",
        "FJ",
        "FI",
        "FR",
        "GA",
        "GM",
        "GE",
        "DE",
        "GH",
        "GR",
        "GD",
        "GT",
        "GN",
        "GW",
        "GY",
        "HT",
        "VA",
        "HN",
        "HU",
        "IS",
        "IN",
        "ID",
        "IQ",
        "IE",
        "IL",
        "IT",
        "JM",
        "JP",
        "JO",
        "KZ",
        "KE",
        "KI",
        "KW",
        "KG",
        "LV",
        "LB",
        "LS",
        "LR",
        "LI",
        "LT",
        "LU",
        "MG",
        "MW",
        "MY",
        "MV",
        "ML",
        "MT",
        "MH",
        "MR",
        "MU",
        "MX",
        "FM",
        "MD",
        "MC",
        "MN",
        "ME",
        "MA",
        "MZ",
        "MM",
        "NA",
        "NR",
        "NP",
        "NL",
        "NZ",
        "NI",
        "NE",
        "NG",
        "MK",
        "NO",
        "OM",
        "PK",
        "PW",
        "PS",
        "PA",
        "PG",
        "PE",
        "PH",
        "PL",
        "PT",
        "QA",
        "RO",
        "RW",
        "KN",
        "LC",
        "VC",
        "WS",
        "SM",
        "ST",
        "SN",
        "RS",
        "SC",
        "SL",
        "SG",
        "SK",
        "SI",
        "SB",
        "ZA",
        "KR",
        "ES",
        "LK",
        "SR",
        "SE",
        "CH",
        "TW",
        "TZ",
        "TH",
        "TL",
        "TG",
        "TO",
        "TT",
        "TN",
        "TR",
        "TV",
        "UG",
        "UA",
        "AE",
        "GB",
        "US",
        "UY",
        "VN",
        "VU",
        "ZM",
    ]
)


def unblock_detect() -> bool:
    try:
        allowed = False
        # check for ChatGPT Web: https://chat.openai.com
        request = urllib.request.Request(
            url=f"https://chat.openai.com/favicon.ico",
            headers=utils.DEFAULT_HTTP_HEADERS,
        )
        response = urllib.request.urlopen(request, timeout=5, context=utils.CTX)
        if response.getcode() == 200:
            # detect current ip location
            content = utils.http_get(url=f"https://chat.openai.com/cdn-cgi/trace", retry=2)
            group = re.findall("loc=([A-Z]{2})", content, flags=re.I)
            location = group[0] if group else ""
            allowed = location in ALLOWED_COUNTRY_CODES

        # check for ChatGPT API: https://api.openai.com
        if allowed:
            request = urllib.request.Request(
                url=f"https://api.openai.com/dashboard/onboarding/login",
                headers=OPTIONS_HEADERS,
                method="OPTIONS",
            )
            response = urllib.request.urlopen(request, timeout=5, context=utils.CTX)
            allowed = response.getcode() == 200

        return allowed
    except Exception:
        return False
