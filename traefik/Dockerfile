ARG BUILD_ARCH=amd64
ARG BUILD_VERSION=0.1.0
ARG TRAEFIK_VERSION=3.3.3

FROM traefik:${TRAEFIK_VERSION} AS traefik

FROM ghcr.io/home-assistant/${BUILD_ARCH}-base:3.21

ARG BUILD_ARCH
ARG BUILD_VERSION
ARG TRAEFIK_VERSION=3.3.3

LABEL \
  org.opencontainers.image.title="Traefik Reverse Proxy Home Assistant Add-on" \
  org.opencontainers.image.description="Traefik ${TRAEFIK_VERSION} reverse proxy add-on for Home Assistant" \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache \
      bash \
      ca-certificates \
      logrotate \
      py3-yaml \
      python3 \
      tzdata

COPY --from=traefik /usr/local/bin/traefik /usr/local/bin/traefik

COPY scripts/addon-entrypoint.py /usr/local/bin/addon-entrypoint.py
COPY scripts/render-traefik-config.py /usr/local/bin/render-traefik-config.py
COPY defaults/ /usr/share/traefik-addon/defaults/

RUN chmod +x \
      /usr/local/bin/addon-entrypoint.py \
      /usr/local/bin/render-traefik-config.py

RUN python3 -c "import yaml" \
    && python3 -m py_compile /usr/local/bin/addon-entrypoint.py \
    && python3 -m py_compile /usr/local/bin/render-traefik-config.py

CMD ["/usr/local/bin/addon-entrypoint.py"]
