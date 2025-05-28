<!--
 * @Author: wzdnzd
 * @Date: 2022-03-06 14:51:29
 * @Description: 
 * Copyright (c) 2022 by wzdnzd, All Rights Reserved.
-->

## 功能
打造免费代理池，爬一切可爬节点
> 拥有灵活的插件系统，如果目标网站特殊，现有功能未能覆盖，可针对性地通过插件实现

> 欢迎 Star 及 PR。对于质量较高且普适的爬取目标，亦可在 Issues 中列出，将在评估后选择性添加

## 使用方法
> 可前往 [Issue #91](https://github.com/wzdnzd/aggregator/issues/91) 食用**共享订阅**，量大质优。**请勿浪费**
 
略，自行探索。我才不会告诉你入口是 `collect.py` 和 `process.py`。**强烈建议使用后者，前者只是个小玩具**，配置参考 `subscribe/config/config.default.json`，详细文档见 [DeepWiki](https://deepwiki.com/wzdnzd/aggregator)

## Docker 部署与 Hugging Face
本项目支持通过 Docker 容器运行。你可以使用 Docker 来轻松部署和管理此应用。以下是一些重要的环境变量，可以在运行 Docker 容器时进行配置：

- `APP_SCHEDULE`: 用于设置 `subscribe/collect.py` 脚本在 Docker 容器内部的定时执行周期 (Cron 格式, 例如 `"0 3 * * *"` 表示每天凌晨3点)。
- `APP_ARGS`: 用于传递给 `subscribe/collect.py` 脚本的参数 (例如 `"--all --overwrite --skip"`)。
- `GIST_PAT`: GitHub Personal Access Token，用于将结果上传到 Gist。
- `GIST_LINK`: GitHub Gist 链接 (格式: `username/gist_id`)，指定上传到的 Gist。
- `CUSTOMIZE_LINK`: 自定义机场列表的 URL 地址。

## 免责申明
+ 本项目仅用作学习爬虫技术，请勿滥用，不要通过此工具做任何违法乱纪或有损国家利益之事
+ 禁止使用该项目进行任何盈利活动，对一切非法使用所产生的后果，本人概不负责

## 致谢
1. <u>[Subconverter](https://github.com/asdlokj1qpi233/subconverter)</u>、<u>[Mihomo](https://github.com/MetaCubeX/mihomo)</u>

2. 感谢 [![YXVM](https://support.nodeget.com/page/promotion?id=250)](https://yxvm.com)
[NodeSupport](https://github.com/NodeSeekDev/NodeSupport) 赞助了本项目