FROM python:3.12-slim AS build

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir --root-user-action=ignore build \
 && python -m build --wheel --outdir /dist

FROM python:3.12-slim

# The S7 port is 102, which is privileged. The container listens on an
# unprivileged port as a non-root user and lets Docker publish it as 102:
#   docker run -p 102:1102 ...
ENV S7SIM_PORT=1102 \
    S7SIM_CONFIG=/etc/s7sim/line.yml \
    PYTHONUNBUFFERED=1

RUN useradd --system --create-home --uid 10001 s7sim

COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir --root-user-action=ignore /tmp/*.whl && rm /tmp/*.whl

COPY examples/line.yml /etc/s7sim/line.yml

USER s7sim
EXPOSE 1102

# A container that answers the protocol is healthy; one that only has a live
# process is not, so the check opens a real connection.
HEALTHCHECK --interval=15s --timeout=10s --start-period=5s --retries=3 \
    CMD s7-sim --config "$S7SIM_CONFIG" --port "$S7SIM_PORT" --health

ENTRYPOINT ["sh", "-c", "exec s7-sim --config \"$S7SIM_CONFIG\" --port \"$S7SIM_PORT\" \"$@\"", "--"]
