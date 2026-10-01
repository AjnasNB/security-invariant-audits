FROM node:24-slim AS node
FROM python:3.13-slim
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && apt-get update && apt-get install -y --no-install-recommends ca-certificates ripgrep libstdc++6 git \
 && rm -rf /var/lib/apt/lists/*
COPY .runtime/codex-release/bin/codex-x86_64-unknown-linux-musl /usr/local/bin/codex
COPY .runtime/claude-release/bin/package/claude /usr/local/bin/claude
RUN chmod 755 /usr/local/bin/codex /usr/local/bin/claude
COPY _sources/openhands_sdk/openhands-sdk /opt/openhands-sdk
COPY _sources/claude_agent_sdk /opt/claude-agent-sdk
RUN pip install --no-cache-dir /opt/openhands-sdk /opt/claude-agent-sdk \
    'pytest==9.0.3' 'pytest-asyncio>=1.3.0' 'trio==0.30.0' \
 && npm install --prefix /opt/codex-test-deps --ignore-scripts --no-audit --no-fund \
    jest@29.7.0 ts-jest@29.4.3 ts-jest-mock-import-meta@1.3.1 \
    typescript@5.9.3 @types/jest@29.5.14 @types/node@22.15.30 ts-node@10.9.2 \
    zod@3.24.4 zod-to-json-schema@3.24.6
COPY harnesses/mcp_proxy.py harnesses/openhands_worker.py /opt/study/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp/home \
    NODE_PATH=/opt/codex-test-deps/node_modules \
    OPENHANDS_HIDE_BANNER=1 LITELLM_LOCAL_MODEL_COST_MAP=True
WORKDIR /task
USER 65534:65534
