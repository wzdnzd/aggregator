# -*- coding: utf-8 -*-

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import utils
from config.models import TwitterConfig
from crawl.base import Channel, register_channel
from crawl.channels.page import PageChannel
from crawl.helpers import fetch_jobs, is_reachable
from crawl.models import ChannelResult, CrawlContext
from logger import logger
from origin import Origin


class TwitterChannel(Channel[TwitterConfig]):
    name = "twitter"

    def crawl(self, config: TwitterConfig, ctx: CrawlContext) -> ChannelResult:
        if not is_reachable("https://twitter.com"):
            logger.warning("[TwitterCrawl] skip because twitter is unreachable")
            return ChannelResult()
        return crawl_twitter(config, ctx)


def extract_twitter_cookies(retry: int = 2) -> str:
    if retry <= 0:
        return ""

    headers = None
    try:
        request = urllib.request.Request(url="https://twitter.com/", headers=utils.DEFAULT_HTTP_HEADERS)
        response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
        headers = response.headers
    except urllib.error.HTTPError as exc:
        if exc.code != 302:
            return extract_twitter_cookies(retry=retry - 1)
        headers = exc.headers
    except (urllib.error.URLError, TimeoutError):
        return extract_twitter_cookies(retry=retry - 1)

    if not headers or "set-cookie" not in headers:
        return ""

    regex = "(guest_id|guest_id_ads|guest_id_marketing|personalization_id)=(.+?);"
    content = ";".join(headers.get_all("set-cookie", ""))
    groups = re.findall(regex, content, flags=re.I)
    return ";".join(["=".join(item) for item in groups]).strip()


def get_guest_token() -> str:
    cookies = extract_twitter_cookies(retry=3)
    if not cookies:
        logger.error("[TwitterCrawl] cannot extract Twitter cookies")
        return ""

    headers = {
        "User-Agent": utils.USER_AGENT,
        "Cookie": cookies,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    }
    content = utils.http_get(url="https://twitter.com/", headers=headers)
    if not content:
        return ""
    matcher = re.findall("gt=([0-9]{19})", content, flags=re.I)
    return matcher[0] if matcher else ""


def username_to_id(username: str, headers: dict[str, str]) -> str:
    if utils.isblank(username):
        return ""

    if not headers or "X-Guest-Token" not in headers:
        guest_token = get_guest_token()
        if not guest_token:
            return ""
        headers = {
            "User-Agent": utils.USER_AGENT,
            "Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
            "X-Guest-Token": guest_token,
            "Content-Type": "application/json",
        }

    variables = {"screen_name": username.lower().strip(), "withSafetyModeUserFields": True}
    features = {
        "blue_business_profile_image_shape_enabled": True,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
    }
    payload = urllib.parse.urlencode({"variables": json.dumps(variables), "features": json.dumps(features)})
    url = f"https://twitter.com/i/api/graphql/sLVLhk0bGj3MVFEKTdax1w/UserByScreenName?{payload}"
    try:
        content = utils.http_get(url=url, headers=headers)
        if not content:
            return ""
        data = json.loads(content).get("data", {}).get("user", {}).get("result", "")
        return data.get("rest_id", "")
    except Exception:
        logger.error(f"[TwitterCrawl] cannot query uid by username=[{username}]")
        return ""


def crawl_twitter(config: TwitterConfig, ctx: CrawlContext) -> ChannelResult:
    if not config or not config.users:
        return ChannelResult()

    guest_token, starttime = get_guest_token(), time.time()
    if not guest_token:
        logger.error("[TwitterCrawl] cannot extract X-Guest-Token from twitter")
        return ChannelResult()

    headers = {
        "User-Agent": utils.USER_AGENT,
        "Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "X-Guest-Token": guest_token,
        "Content-Type": "application/json",
    }
    features = {
        "blue_business_profile_image_shape_enabled": True,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "tweetypie_unmention_optimization_enabled": True,
        "vibe_api_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "tweet_awards_web_tipping_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": False,
        "interactive_text_enabled": True,
        "responsive_web_text_conversations_enabled": False,
        "longform_notetweets_rich_text_read_enabled": True,
        "responsive_web_enhance_cards_enabled": False,
    }

    candidates = {key: value for key, value in config.users.items() if key and value.enable and value.push_to}
    if not candidates:
        return ChannelResult()

    params = [[key, headers] for key in candidates.keys()]
    uids = utils.multi_thread_run(func=username_to_id, tasks=params, num_threads=ctx.num_threads)
    jobs = []
    for index, uid in enumerate(uids):
        if not uid:
            continue
        config = candidates.get(params[index][0], {})
        count = config.tweets
        variables = {
            "userId": uid,
            "count": min(max(count, 1), 100),
            "includePromotedContent": False,
            "withClientEventToken": False,
            "withBirdwatchNotes": False,
            "withVoice": True,
            "withV2Timeline": True,
        }
        payload = urllib.parse.urlencode({"variables": json.dumps(variables), "features": json.dumps(features)})
        url = f"https://twitter.com/i/api/graphql/P7qs2Sf7vu1LDKbzDW9FSA/UserMedia?{payload}"
        jobs.append(
            PageChannel(
                url=url,
                include=config.include,
                exclude=config.exclude,
                push_to=config.push_to,
                task=config.task,
                headers=headers,
                origin=Origin.TWITTER.name,
            )
        )

    result = fetch_jobs(jobs, ctx)
    logger.info(
        f"[TwitterCrawl] finished crawl from Twitter, found {len(result.items)} subscriptions, cost: {time.time() - starttime:.2f}s"
    )
    return result


register_channel(TwitterChannel())
