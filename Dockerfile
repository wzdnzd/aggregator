# build: docker buildx build --platform linux/amd64 -f Dockerfile -t wzdnzd/aggregator:tag --build-arg PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple" .

FROM python:3.12.3-slim

LABEL maintainer="wzdnzd"

ARG PIP_INDEX_URL="https://pypi.org/simple"

# Install system dependencies (as root)
RUN apt-get update && apt-get install -y cronie tzdata --no-install-recommends && rm -rf /var/lib/apt/lists/*

# User Setup
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# Environment variables
ENV GIST_LINK=""
ENV CUSTOMIZE_LINK=""
ENV APP_SCHEDULE="0 3 * * *"
ENV APP_ARGS="--all --overwrite --skip"
ENV GIST_PAT=""

# File Copying and Python Dependencies (as user)
COPY --chown=user ./requirements.txt requirements.txt
RUN pip install -i ${PIP_INDEX_URL} --no-cache-dir -r requirements.txt

COPY --chown=user subscribe /app/subscribe
COPY --chown=user clash/clash-linux-amd /app/clash/clash-linux-amd
COPY --chown=user clash/Country.mmdb /app/clash/Country.mmdb
COPY --chown=user subconverter /app/subconverter

# Remove unnecessary platform-specific binaries from subconverter
RUN rm -rf /app/subconverter/subconverter-darwin-amd \
    && rm -rf /app/subconverter/subconverter-darwin-arm \
    && rm -rf /app/subconverter/subconverter-linux-arm \
    && rm -rf /app/subconverter/subconverter-windows.exe

# Copy and set permissions for the cron script
COPY --chown=user scripts/run-cron.sh /app/run-cron.sh
RUN chmod +x /app/run-cron.sh

# start and run
CMD ["/app/run-cron.sh"]
