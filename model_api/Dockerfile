# Production image for the Model API (LiteLLM Proxy + Gooey auth), deployed as
# its own CapRover app via model-api.captain-definition at the repo root.
#
# It installs model_api/poetry.lock (not the root lock) into its own
# virtualenv, and copies the whole repo: the Proxy loads Django and Gooey's
# auth and workspace apps in-process.
FROM library/python:3.10.12-slim-bookworm

# gRPC has a separate bundled CA store; use the patched system roots.
ENV GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=/etc/ssl/certs/ca-certificates.crt

ENV WORKDIR /app
WORKDIR $WORKDIR

# system packages the Django apps and their Python dependencies need
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential \
    poppler-utils \
    libpoppler-dev \
    libpoppler-cpp-dev \
    pandoc \
    libmagickwand-dev \
    libgl1-mesa-glx \
    python3-opencv \
    postgresql-client \
    ffmpeg \
    libzbar0 \
    curl \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' ca-certificates)" ge 20250419~deb12u2 \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/model-api-venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY ./model_api/pyproject.toml ./model_api/poetry.lock /opt/model-api/
# Bootstrap pip with the hash from the Python security announcement.
RUN python -m pip install --no-cache-dir "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70" \
    && python -m pip install --no-cache-dir -U poetry "certifi>=2026.10.19" \
    && python -m venv $VIRTUAL_ENV \
    && cd /opt/model-api \
    && poetry install --no-cache --only main --no-interaction --no-root

COPY . .

ENV PYTHONPATH=$WORKDIR
ENV PYTHONUNBUFFERED=1
# settings default DEBUG to True; production never wants it (and Django's
# debug profiler writes to a media dir this image doesn't have)
ENV DEBUG=False
ENV FORWARDED_ALLOW_IPS='*'
ENV PORT=8000

# the Proxy's admin UI and API docs stay off; prices change only when LiteLLM
# is upgraded, not on every start
ENV DISABLE_ADMIN_UI=True
ENV NO_DOCS=True
ENV NO_REDOC=True
ENV LITELLM_LOCAL_MODEL_COST_MAP=True

ARG CAPROVER_GIT_COMMIT_SHA=${CAPROVER_GIT_COMMIT_SHA}
ENV CAPROVER_GIT_COMMIT_SHA=${CAPROVER_GIT_COMMIT_SHA}

EXPOSE 8000

HEALTHCHECK CMD curl -fsS "127.0.0.1:${PORT}/health/liveliness" || exit 1

CMD ["sh", "-c", "test -n \"$OPENAI_API_KEY\" || { echo 'model-api: set OPENAI_API_KEY' >&2; exit 1; }; exec litellm --config model_api/proxy_config.yaml --host 0.0.0.0 --port \"$PORT\" --telemetry False"]
