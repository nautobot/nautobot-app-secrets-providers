ARG NAUTOBOT_VER="1.2.1"
ARG PYTHON_VER=3.8
FROM ghcr.io/nautobot/nautobot-dev:${NAUTOBOT_VER}-py${PYTHON_VER}

ENV prometheus_multiproc_dir=/prom_cache

ARG NAUTOBOT_ROOT=/opt/nautobot

ENV NAUTOBOT_ROOT ${NAUTOBOT_ROOT}

WORKDIR $NAUTOBOT_ROOT

# Configure poetry
RUN poetry config virtualenvs.create false \
    && poetry config installer.parallel false

# -------------------------------------------------------------------------------------
# Install Nautobot Plugin
# -------------------------------------------------------------------------------------
WORKDIR /tmp

# Copy in only pyproject.toml/poetry.lock to help with caching this layer if no updates to dependencies
COPY poetry.lock pyproject.toml /tmp/
# --no-root declares not to install the project package since we're wanting to take advantage of caching dependency installation
# and the project is copied in and installed after this step
RUN poetry add nautobot=$NAUTOBOT_VER && \
    poetry update --lock && \
    poetry install --no-interaction --no-ansi --no-root

WORKDIR /source

# Copy in the rest of the source code and install local Nautobot plugin
COPY . /source
RUN mv /tmp/poetry.lock /tmp/pyproject.toml /source && \
    poetry install --no-interaction --no-ansi

COPY development/nautobot_config.py ${NAUTOBOT_ROOT}/nautobot_config.py
