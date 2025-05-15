#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from datetime import datetime
from utils.logger import logger
import os

class GistService:
    def __init__(self):
        self.subscriptions_file = "subscriptions.json"

    def load_subscriptions(self):
        """从本地文件加载订阅信息"""
        try:
            logger.info(f"开始从本地文件加载订阅信息: {self.subscriptions_file}")
            
            # 检查文件是否存在
            if not os.path.exists(self.subscriptions_file):
                logger.info("首次运行，创建新的订阅文件")
                return {"subscriptions": []}
                
            with open(self.subscriptions_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    logger.info("订阅文件为空，创建新的订阅列表")
                    return {"subscriptions": []}
                
                data = json.loads(content)
                logger.info(f"成功加载订阅信息，当前共有 {len(data.get('subscriptions', []))} 个订阅")
                return data
        except Exception as e:
            logger.error(f"加载订阅信息失败: {e}")
            return {"subscriptions": []}

    def save_subscriptions(self, data):
        """保存订阅信息到本地文件"""
        try:
            # 确保数据格式正确
            if "subscriptions" not in data:
                data = {"subscriptions": []}
            
            logger.info(f"开始保存订阅信息，当前共有 {len(data['subscriptions'])} 个订阅")
            
            with open(self.subscriptions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            logger.info("订阅信息保存成功")
        except Exception as e:
            logger.error(f"保存订阅信息失败: {e}")

    def update_subscription_status(self, subscription, fetch_nodes_func):
        """更新订阅状态"""
        logger.info(f"更新订阅状态: {subscription['url']}")
        if fetch_nodes_func(subscription['url']):
            subscription['last_success'] = datetime.now().isoformat()
            subscription['failure_count'] = 0
            subscription['last_check'] = datetime.now().isoformat()
            logger.info(f"订阅更新成功: {subscription['url']}")
            return True
        else:
            subscription['failure_count'] = subscription.get('failure_count', 0) + 1
            subscription['last_check'] = datetime.now().isoformat()
            if not subscription.get('first_failure'):
                subscription['first_failure'] = datetime.now().isoformat()
            logger.warning(f"订阅更新失败: {subscription['url']}, 失败次数: {subscription['failure_count']}")
            return False 