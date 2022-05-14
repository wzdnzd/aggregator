<!--
 * @Author: wzdnzd
 * @Date: 2022-03-06 14:51:29
 * @Description: 
 * Copyright (c) 2022 by wzdnzd, All Rights Reserved.
-->
# 机场自动签到脚本，支持多个机场签到

> 说明: 
> + `auto-checkin.py`用于基于SS-Panel搭建的机场签到，`renewal.py`用于基于V2Board搭建的机场订阅续期
> + 支持`Python2` 和 `Python3`
> + 目前不支持任何带有验证码（登陆或签到时需要输入验证码）功能的机场
> + 用户名及密码转base64编码可使用[Base64在线编码解码](https://base64.us)

## 使用方法
### 1. 利用Github Actions签到（推荐）
+ 点击右上角`Fork`克隆本项目
+ 修改项目为私有，具体方法见[Github更改仓库的可见性](https://docs.github.com/cn/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility#changing-a-repositorys-visibility)
+ 编辑`.github/actions/checkin/config.json`，填写base64编码后的邮箱及密码
+ 若要修改签到时间，可修改`.github/workflows/checkin.yml`文件的`cron`配置
![修改签到时间](https://s1.ax1x.com/2022/05/14/Oc6H56.png)

### 2. 本地运行
+ 克隆代码库
 ```shell
git clone https://github.com/wzdnzd/ssr-checkin.git
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
+ `windows` 操作系统可通过 `任务计划程序` 添加到定时任务，详见[Windows系统中设置Python程序定时运行](https://www.itcodemonkey.com/article/6098.html)
+ `Linux` 或 `MacOS` 可通过 `cron` 添加到定时任务（或登陆启动项），详见[利用Linux的crontab实现定时执行python任务](https://www.aisun.org/2018/07/linux+crontab+python/)
