# SSR机场自动签到脚本（适用于大部分基于SS-Panel的机场）

> Note: 
> + 支持`Python2` 和 `Python3`
> + 目前不支持任何带有验证码（登陆或签到时需要输入验证码）功能的机场

## Usage
+ 修改 `config.json` 配置文件
```json
proxyServer: 代理服务器地址，非必需

waitTime: 0 ~ 20，模拟任意时间签到，非必需

retry: 失败时重试次数，非必需

domains：支持多个机场，必须

domain：机场主域名，必须

proxy：true | false，是否使用代理

email：注册时使用的email

password：密码
```
+ `windows` 操作系统可通过 `任务计划程序` 添加到定时任务，详见[Windows系统中设置Python程序定时运行](https://www.itcodemonkey.com/article/6098.html)
+ `Linux` 或 `MacOS` 可通过 `cron` 添加到定时任务（或登陆启动项），详见[利用Linux的crontab实现定时执行python任务](https://www.aisun.org/2018/07/linux+crontab+python/)