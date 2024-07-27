# build: docker buildx build --platform linux/amd64 -f Dockerfile -t wzdnzd/aggregator:tag .

FROM arm64v8/ubuntu:latest

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
