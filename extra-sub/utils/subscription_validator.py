#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
from .logger import logger

def is_proxy_uri_list(content):
    """检查是否为代理 URI 列表"""
    protocols = ('ss://', 'ssr://', 'vmess://', 'trojan://', 'vless://', 'hysteria://', 'hysteria2://', 'tuic://')
    lines = content.splitlines()
    count = 0
    for line in lines:
        line = line.strip()
        if any(line.startswith(proto) for proto in protocols):
            count += 1
    return count > 0

def is_clash_config(content):
    """检查是否为 Clash 配置"""
    try:
        # 检查是否包含 Clash 配置的关键特征
        clash_features = [
            'proxies:',
            'proxy-groups:',
            'rules:',
            'port:',
            'socks-port:',
            'allow-lan:',
            'mode:',
            'log-level:'
        ]
        return any(feature in content for feature in clash_features)
    except:
        return False

def is_surge_config(content):
    """检查是否为 Surge 配置"""
    surge_features = [
        '[Proxy]',
        '[Rule]',
        '[General]',
        '[Host]',
        '[URL Rewrite]',
        '[MITM]'
    ]
    return any(feature in content for feature in surge_features)

def is_quantumult_config(content):
    """检查是否为 Quantumult 配置"""
    quantumult_features = [
        '[server_local]',
        '[server_remote]',
        '[filter_local]',
        '[filter_remote]',
        '[rewrite_local]',
        '[rewrite_remote]',
        '[mitm]'
    ]
    return any(feature in content for feature in quantumult_features)

def is_shadowrocket_config(content):
    """检查是否为 Shadowrocket 配置"""
    # 检查是否包含常见的代理配置特征
    if 'http://' in content or 'https://' in content:
        # 进一步检查是否包含 Shadowrocket 特有的配置
        shadowrocket_features = [
            'ss://',
            'vmess://',
            'trojan://',
            'http-proxy',
            'https-proxy',
            'bypass-tun'
        ]
        return any(feature in content for feature in shadowrocket_features)
    return False

def try_b64_decode(content):
    """尝试 Base64 解码"""
    try:
        # 标准Base64解码
        content_bytes = content.encode('utf-8')
        missing_padding = len(content_bytes) % 4
        if missing_padding:
            content_bytes += b'=' * (4 - missing_padding)
        decoded = base64.b64decode(content_bytes).decode('utf-8')
        return decoded
    except:
        try:
            # URL安全的Base64解码
            decoded = base64.urlsafe_b64decode(content.encode('utf-8')).decode('utf-8')
            return decoded
        except:
            return None

def is_valid_subscription_content(content):
    """验证订阅内容是否有效"""
    try:
        # 检查内容是否为空
        if not content or not content.strip():
            logger.warning("订阅内容为空")
            return False

        # 尝试Base64解码并检查
        decoded = try_b64_decode(content)
        if decoded:
            if (is_proxy_uri_list(decoded) or
                is_clash_config(decoded) or
                is_surge_config(decoded) or
                is_quantumult_config(decoded) or
                is_shadowrocket_config(decoded)):
                logger.info("检测到有效的订阅内容（Base64编码）")
                return True

        # 检查原始内容是否为已知格式
        if (is_proxy_uri_list(content) or
            is_clash_config(content) or
            is_surge_config(content) or
            is_quantumult_config(content) or
            is_shadowrocket_config(content)):
            logger.info("检测到有效的订阅内容")
            return True

        logger.warning("未检测到有效的订阅格式")
        return False

    except Exception as e:
        logger.error(f"验证订阅内容时出错: {e}")
        return False 