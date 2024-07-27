FROM python:3.9-slim as builder
 
# 安装编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        libssl-dev \
        make \
    && rm -rf /var/lib/apt/lists/*
 
# 安装Python依赖
RUN pip install --no-cache-dir -U pip setuptools
 
# 第二阶段，从builder阶段复制构建好的Python环境到最终的ARM镜像
FROM arm32v7/python:3.9-slim
 
# 复制构建阶段中安装的Python环境
COPY --from=builder /usr/local /usr/local
MAINTAINER wzdnzd

# github personal access token
ENV GIST_PAT=""

# github gist info, format: username/gist_id
ENV GIST_LINK=""

# customize airport listing url address
ENV CUSTOMIZE_LINK=""

WORKDIR /aggregator

# copy files, only linux related files are needed
COPY requirements.txt /aggregator
COPY subscribe /aggregator/subscribe 
COPY clash/clash-linux-amd clash/Country.mmdb /aggregator/clash

COPY subconverter /aggregator/subconverter
RUN rm -rf subconverter/subconverter-darwin-amd \
    && rm -rf subconverter/subconverter-darwin-arm \
    && rm -rf subconverter/subconverter-linux-arm \
    && rm -rf subconverter/subconverter-windows.exe

# install dependencies
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir -r requirements.txt

# start and run
CMD ["python", "-u", "subscribe/collect.py", "--all", "--overwrite", "--skip"]
