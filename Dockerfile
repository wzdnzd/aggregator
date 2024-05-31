# build: docker buildx build --platform linux/amd64 -f Dockerfile -t wzdnzd/aggregator:tag .

FROM python:3.12.3-slim

MAINTAINER wzdnzd

# github personal access token
ENV GIST_PAT=""

# github gist info, format: username/gist_id
ENV GIST_LINK=""

WORKDIR /aggregator

# copy files, only linux related files are needed
COPY requirements.txt /aggregator
COPY subscribe /aggregator/subscribe 
COPY clash/clash-linux clash/Country.mmdb /aggregator/clash

COPY subconverter /aggregator/subconverter
RUN rm -rf subconverter/subconverter-darwin \
    && rm -rf subconverter/subconverter-windows.exe

# install dependencies
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir -r requirements.txt

# start and run
CMD ["python", "-u", "subscribe/collect.py", "--all", "--both", "--overwrite", "--skip"]