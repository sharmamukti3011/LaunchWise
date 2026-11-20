# Frontend image: builds the React app, then serves it with Caddy, which is also the reverse
# proxy and the HTTPS terminator. Build from the repo root: docker build -f frontend/Dockerfile .
# Both base images are pinned to a version tag, not a digest, so rebuilds pick up patch releases.

FROM node:24-alpine AS build
WORKDIR /build
RUN chown node:node /build
USER node
COPY --chown=node:node frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY --chown=node:node frontend/index.html frontend/404.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY --chown=node:node frontend/src ./src
# Favicons, the logo and the web manifest: Vite copies public/ to the site root.
COPY --chown=node:node frontend/public ./public
RUN npm run build

FROM caddy:2-alpine
# A fixed non-root user. Caddy keeps certificates in /data and its config in /config; both are
# volumes in docker-compose.yml so certificates survive restarts.
RUN addgroup -S -g 10002 caddy-app \
    && adduser -S -u 10002 -G caddy-app -H -h /nonexistent caddy-app \
    && mkdir -p /data /config \
    && chown caddy-app:caddy-app /data /config
ENV XDG_DATA_HOME=/data \
    XDG_CONFIG_HOME=/config
COPY --from=build /build/dist /srv
COPY frontend/Caddyfile /etc/caddy/Caddyfile

USER caddy-app
EXPOSE 80 443
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
