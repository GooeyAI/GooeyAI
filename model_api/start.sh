#!/bin/sh
# Starts the Model API (LiteLLM Proxy) on $PORT (default 8090).
#
# The Proxy refuses to start without a strong master key, which nothing uses
# (see proxy_config.yaml), so it gets a fresh random one on each start.
set -e
export LITELLM_MASTER_KEY="sk-$(openssl rand -hex 32)"
exec litellm --config model_api/proxy_config.yaml --host 0.0.0.0 --port "${PORT:-8090}" --telemetry False
