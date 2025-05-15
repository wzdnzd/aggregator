#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from urllib.parse import parse_qs, urlparse
from .logger import logger

def is_valid_subscription_url(url):
    """验证订阅链接的有效性"""
    try:
        parsed = urlparse(url)
        # 检查是否是有效的 URL
        if not all([parsed.scheme, parsed.netloc]):
            logger.debug(f"无效的 URL 格式: {url}")
            return False
            
        # 检查是否是已知的订阅协议
        valid_schemes = ['http', 'https', 'ss', 'ssr', 'vmess', 'trojan', 'vless', 'snell', 'hysteria2', 'hysteria', 'tuic']
        if parsed.scheme not in valid_schemes:
            logger.debug(f"不支持的协议: {url}")
            return False
            
        # 检查域名格式
        domain_pattern = r"^(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+$"
        if not re.match(domain_pattern, parsed.netloc):
            logger.debug(f"无效的域名格式: {url}")
            return False
            
        # 检查是否是已知的订阅路径
        valid_paths = [
            '/api/v1/client/subscribe',
            '/link/',
            '/s/',
            '/sub/',
            '/sub?',
            '/getsub.php'
        ]
        
        # 检查路径和查询参数
        path = parsed.path.lower()
        query = parsed.query.lower()
        
        # 检查路径
        if not any(p in path for p in valid_paths):
            # 检查查询参数
            if not any(p in query for p in ['token=', 'sub=', 'mu=', 'clash=', 'service=', 'id=']):
                logger.debug(f"不支持的路径或参数: {url}")
                return False
        
        # 检查域名
        invalid_domains = ['example.com', 'localhost', '127.0.0.1']
        if any(d in parsed.netloc.lower() for d in invalid_domains):
            logger.debug(f"无效的域名: {url}")
            return False
            
        logger.debug(f"有效的订阅链接: {url}")
        return True
    except Exception as e:
        logger.debug(f"验证链接时出错 {url}: {e}")
        return False

def extract_subscription_links(message):
    """从消息中提取订阅链接"""
    logger.debug(f"开始从消息中提取链接: {message[:100]}...")
    
    # 清理消息文本
    message = message.strip()
    if not message:
        return []
        
    # 定义正则表达式模式
    # 标准订阅链接模式
    sub_regex = r"https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+(?:(?:(?:/index.php)?/api/v1/client/subscribe\?token=[a-zA-Z0-9]{16,32})|(?:/link/[a-zA-Z0-9]+\?(?:sub|mu|clash)=\d)|(?:/(?:s|sub)/[a-zA-Z0-9]{32}))|https://jmssub\.net/members/getsub\.php\?service=\d+&id=[a-zA-Z0-9\-]{36}(?:\S+)?"
    
    # 额外订阅链接模式
    extra_regex = r"https?://(?:[a-zA-Z0-9\u4e00-\u9fa5\-]+\.)+[a-zA-Z0-9\u4e00-\u9fa5\-]+/sub\?(?:\S+)?target=\S+"
    
    # 协议链接模式
    protocal_regex = r"(?:vmess|trojan|ss|ssr|snell|hysteria2|vless|hysteria|tuic)://[a-zA-Z0-9:.?+=@%&#_\-/]{10,}"
    
    # 合并订阅链接模式
    regex = f"{sub_regex}|{extra_regex}"
    
    try:
        # 提取订阅链接
        subscribes = re.findall(regex, message, flags=re.I)
        logger.debug(f"找到 {len(subscribes)} 个订阅链接")
        
        # 提取协议链接
        proxies = re.findall(protocal_regex, message, flags=re.I)
        logger.debug(f"找到 {len(proxies)} 个协议链接")
        
        # 处理所有链接
        valid_urls = []
        seen = set()
        
        # 处理订阅链接
        for sub in subscribes:
            items = [sub]
            # 处理 subconverter url
            if "url=" in sub:
                try:
                    qs = urlparse(sub.replace("&amp;", "&")).query
                    urls = parse_qs(qs).get("url", [])
                    if urls:
                        for url in urls:
                            if is_valid_subscription_url(url):
                                items.extend([x for x in url.split("|") if is_valid_subscription_url(x)])
                except Exception as e:
                    logger.error(f"处理 subconverter URL 时出错: {e}")
            
            # 处理每个链接
            for s in items:
                s = re.sub(r"\\/|\/", "/", s, flags=re.I).strip()
                if not s or s in seen:
                    continue
                seen.add(s)
                
                if is_valid_subscription_url(s):
                    valid_urls.append(s)
                    logger.debug(f"找到有效订阅链接: {s}")
        
        # 处理协议链接
        for proxy in proxies:
            proxy = proxy.lower().strip()
            if proxy and proxy not in seen:
                seen.add(proxy)
                if is_valid_subscription_url(proxy):
                    valid_urls.append(proxy)
                    logger.debug(f"找到有效协议链接: {proxy}")
        
        logger.info(f"从消息中提取到 {len(valid_urls)} 个有效链接")
        return valid_urls
        
    except Exception as e:
        logger.error(f"提取订阅链接时出错: {e}")
        return [] 