## 说明

对于 Apple 的一些被动或主动屏蔽的服务如 Web Preview、Moveis Trailers、Dictionary 的维基百科查询均已收录于 `Global.list` 进行代理。

该目录只是**一时兴起**想做一些关于 Apple 各子域名具体作用的收录，所以一些分流文件如 `TestFlight.list`、`FindMy.list` 并没有实际意义。

另外，个人**主观认为**鉴于 Apple 在国内大体良好的 CDN 部署个人不建议对其进行代理，当然既然进到了这个目录可能 Apple 的某些服务在你所在地区堪忧，相比以前对于 Apple 整体域名全部代理，该目录收录的一些细分分流文件如 App Store 应用下载、系统更新的专项代理应该更适合你。

### 分流文件说明

**Apple.list**

是 Apple 服务的总体整理，如想对 Apple 服务均进行代理可以使用该分流文件，需要注意的是建议放置于 `Global.list` 之后，因 `Global.list` 有 Apple 对于中国大陆不可用服务的代理行为，如您的 Apple 策略经常在使用直连时会导致 `Global.list` 中的规则失效。

**其他**

`Apple.list` 以外的分流文件基本用于代理策略，文件名极其内容已说明其主要作用。