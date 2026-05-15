ARG MATTERJS_SERVER_VERSION=stable

FROM ghcr.io/matter-js/matterjs-server:${MATTERJS_SERVER_VERSION}

ARG BUILD_ARCH=amd64
ARG BUILD_VERSION=0.1.0
ARG MATTERJS_SERVER_VERSION=stable

LABEL \
  org.opencontainers.image.title="Matter Server Home Assistant Add-on" \
  org.opencontainers.image.description="Matter Server add-on for Home Assistant" \
  org.opencontainers.image.source="https://github.com/AndreySimokhin/home-assistant-addons/tree/main/matter-server" \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}" \
  io.hass.base_image="ghcr.io/matter-js/matterjs-server:${MATTERJS_SERVER_VERSION}"

USER root

COPY scripts/addon-entrypoint.mjs /usr/local/bin/addon-entrypoint.mjs

RUN chmod +x /usr/local/bin/addon-entrypoint.mjs

ENTRYPOINT ["node", "--enable-source-maps", "/usr/local/bin/addon-entrypoint.mjs"]
CMD []
