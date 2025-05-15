#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import time
import requests
import html
from datetime import datetime
from utils.logger import logger
from utils.url_validator import extract_subscription_links

class TelegramService:
    def __init__(self, channels):
        self.channels = channels

    def process_telegram_messages(self, gist_service):
        """处理 Telegram 历史消息"""
        logger.info(f"开始处理 Telegram 消息，频道: {self.channels}")
        data = gist_service.load_subscriptions()
        existing_urls = {sub['url'] for sub in data.get('subscriptions', [])}
        new_links_found = False
        
        for channel_username in self.channels:
            try:
                logger.info(f"正在处理频道: {channel_username}")
                channel_name = channel_username.replace('t.me/', '')
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                }
                
                # 获取历史消息
                messages = []
                current_loop = 0
                max_loop = 4
                total_messages = 0
                max_messages = 100
                
                while total_messages < max_messages and current_loop < max_loop:
                    try:
                        current_loop += 1
                        
                        # 构建 API URL
                        api_url = f"https://t.me/s/{channel_name}" if current_loop == 1 else f"https://t.me/s/{channel_name}?before={min_id}"
                        response = requests.get(api_url, headers=headers)
                        response.raise_for_status()
                        
                        # 提取所有消息 ID
                        post_ids = re.findall(rf'data-post="{channel_name}/(\d+)"', response.text)
                        if not post_ids:
                            logger.info("没有找到更多消息")
                            break
                            
                        # 转换为整数并找到最小 ID
                        post_ids = [int(id) for id in post_ids]
                        min_id = min(post_ids)
                        logger.info(f"当前页面最小消息 ID: {min_id}")
                        
                        # 提取消息文本
                        text_matches = re.findall(r'<div class="tgme_widget_message_text js-message_text"(.*?)>(.*?)</div>', response.text, re.DOTALL)
                        
                        if not text_matches:
                            logger.info("没有更多消息了")
                            break
                            
                        # 处理消息
                        for attrs, text in text_matches:
                            # 清理 HTML 标签和实体
                            message = re.sub(r'<[^>]+>', '', text)
                            message = html.unescape(message)
                            messages.append(message)
                            
                        total_messages += len(text_matches)
                        logger.info(f"已获取 {total_messages} 条消息")
                        
                        # 添加延迟，避免请求过快
                        time.sleep(1)
                        
                    except Exception as e:
                        logger.error(f"获取历史消息时出错: {e}")
                        break
                
                logger.info(f"从频道 {channel_username} 获取到 {len(messages)} 条消息")
                
                # 处理消息
                for i, message in enumerate(messages, 1):
                    logger.debug(f"处理第 {i} 条消息: {message[:100]}...")
                    new_links = extract_subscription_links(message)
                    
                    for link in new_links:
                        if link not in existing_urls:
                            logger.info(f"发现新订阅链接: {link}")
                            if 'subscriptions' not in data:
                                data['subscriptions'] = []
                            data['subscriptions'].append({
                                'url': link,
                                'source': channel_username,
                                'found_date': datetime.now().isoformat(),
                                'status': 'active',
                                'failure_count': 0
                            })
                            existing_urls.add(link)
                            new_links_found = True
                
            except Exception as e:
                logger.error(f"处理频道 {channel_username} 时出错: {e}")
                continue
        
        if new_links_found:
            gist_service.save_subscriptions(data)
            logger.info("已保存新发现的订阅链接")
        else:
            logger.info("未发现新的订阅链接") 