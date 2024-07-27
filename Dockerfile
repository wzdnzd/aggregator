FROM python:3.12.3-slim
MAINTAINER wzdnzd

# GitHub 个人访问令牌
ENV GIST_PAT=""

# GitHub gist 信息，格式：用户名/gist_id
ENV GIST_LINK=""

# 自定义机场列表 URL 地址
ENV CUSTOMIZE_LINK="https://raw.githubusercontent.com/shipeng101/aggregator/main/list.txt"

WORKDIR /aggregator

# 复制文件，仅需与 Linux 相关的文件
COPY requirements.txt /aggregator
COPY subscribe /aggregator/subscribe
COPY clash/clash-linux-arm clash/Country.mmdb /aggregator/clash

COPY subconverter /aggregator/subconverter
RUN rm -rf subconverter/subconverter-darwin-amd \
    && rm -rf subconverter/subconverter-darwin-arm \
    && rm -rf subconverter/subconverter-linux-arm \
    && rm -rf subconverter/subconverter-windows.exe

# 安装依赖项
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir -r requirements.txt

# 启动并运行
CMD ["python", "-u", "subscribe/collect.py", "--all", "--overwrite", "--skip"]
