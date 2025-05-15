#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging

def setup_logger():
    """配置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

logger = setup_logger() 