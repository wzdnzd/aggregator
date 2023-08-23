<!--
 * @Author: wzdnzd
 * @Date: 2022-03-06 14:51:29
 * @Description: 
 * Copyright (c) 2022 by wzdnzd, All Rights Reserved.
-->

> 说明: 
> + `auto-checkin.py`用于基于SS-Panel搭建的机场签到，`renewal.py`用于基于V2Board搭建的机场订阅续期
> + 支持`Python2` 和 `Python3`
> + 目前不支持任何带有验证码（登陆或签到时需要输入验证码）功能的机场
> + 对于本项目来说，签到是最不起眼的一个小功能。如果你喜欢探索，你将获得如下成果。
<img width="1168" alt="a" src="https://github.com/wzdnzd/aggregator/assets/8565764/f75b8057-fa86-4d5c-a19f-fe3100ca853f">

## 免责申明
+ 本项目仅用作学习爬虫技术，请勿滥用。
+ 禁止使用该项目进行任何盈利活动，对一切非法使用所产生的后果，本人概不负责。

## 自动签到使用方法（支持多个机场）
### 1. 利用Github Actions签到（推荐）
+ 点击右上角`Fork`克隆本项目
+ ~~修改项目为私有，具体方法见[Github更改仓库的可见性](https://docs.github.com/cn/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility#changing-a-repositorys-visibility)~~
+ ~~编辑`.github/actions/checkin/config.json`，填写机场域名、邮箱及密码~~
+ **设置密钥：分别添加名（即`Name`）为 `AP_DOMAINS`、`AP_EMAILS`、`AP_PASSWORDS` 的密钥并填写对应的值（即`Value`）。如有多个账号(不论是同一机场与否)，需要在 `Value` 栏里一一填写并用 `||` 隔开**
[![添加密钥](https://s1.ax1x.com/2022/08/14/vNWxoj.png)](https://imgtu.com/i/vNWxoj)
[![密钥](https://s1.ax1x.com/2022/08/14/vU1lng.png)](https://imgtu.com/i/vU1lng)
+ 若要修改签到时间，可修改`.github/workflows/checkin.yml`文件的`cron`配置
[![修改签到时间](https://s1.ax1x.com/2022/08/14/vUSkjS.png)](https://imgtu.com/i/vUSkjS)
+ 在 Actions 页面启用 workflow，可先手动触发运行一次验证配置是否正确
[![手动触发](https://s1.ax1x.com/2022/08/14/vUlBFI.png)](https://imgtu.com/i/vUlBFI)

### 2. 本地运行
+ 克隆代码库
 ```shell
git clone https://github.com/wzdnzd/aggregator.git
```
+ 安装依赖库
```shell
pip install -U requests
```
+ 修改 `config.json` 配置文件
```ini
proxyServer: 代理服务器地址，非必需

waitTime: 0 ~ 24，模拟任意时间签到，非必需

retry: 失败时重试次数，非必需

domains：支持多个机场，必须

domain：机场主域名，必须

proxy：true | false，是否使用代理

email：注册时使用的email

password：密码
```
+ `windows` 操作系统可通过 `任务计划程序` 添加到定时任务，详见[Windows系统中设置Python程序定时运行](https://blog.csdn.net/CaiJin1217/article/details/81453940)
+ `Linux` 或 `MacOS` 可通过 `cron` 添加到定时任务（或登陆启动项），详见[利用Linux的crontab实现定时执行python任务](https://bbs.huaweicloud.com/blogs/333192)
