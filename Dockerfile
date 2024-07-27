# Use buildx to build multi-architecture images
# build: docker buildx build --platform linux/amd64,linux/arm64 -f Dockerfile -t wzdnzd/aggregator:tag .

# Define separate stages for amd64 and arm64
FROM --platform=linux/amd64 python:3.12.3-slim AS amd64
FROM --platform=linux/arm64 arm64v8/python:3.12.3-slim AS arm64

MAINTAINER wzdnzd

# Common environment variables
ENV GIST_PAT=""
ENV GIST_LINK=""
ENV CUSTOMIZE_LINK=""

WORKDIR /aggregator

# Copy files for both architectures
COPY requirements.txt /aggregator
COPY subscribe /aggregator/subscribe 
COPY clash/clash-linux-amd clash/Country.mmdb /aggregator/clash
COPY clash/clash-linux-arm clash/Country.mmdb /aggregator/clash
COPY subconverter /aggregator/subconverter

# Remove unnecessary files for both architectures
RUN rm -rf subconverter/subconverter-darwin-amd \
    && rm -rf subconverter/subconverter-darwin-arm \
    && rm -rf subconverter/subconverter-linux-amd \
    && rm -rf subconverter/subconverter-linux-arm \
    && rm -rf subconverter/subconverter-windows-amd.exe

# Install dependencies for both architectures
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir -r requirements.txt

# Start and run command for both architectures
CMD ["python", "-u", "subscribe/collect.py", "--all", "--overwrite", "--skip"]
