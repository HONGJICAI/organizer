# ── Stage 1: build SvelteKit static site ──────────────────────────────────────
FROM node:lts-alpine AS fe-builder
WORKDIR /build/fe
COPY fe/package*.json ./
RUN npm pkg delete scripts.prepare && npm ci
COPY fe/ ./
RUN npm run build

# ── Stage 2: production runtime ───────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.13-alpine

RUN apk add --no-cache nginx supervisor

# ── Backend ──
WORKDIR /app/be
COPY be/pyproject.toml be/uv.lock ./
RUN apk add --no-cache gcc python3-dev musl-dev linux-headers && \
    uv pip install --system --no-cache -r pyproject.toml
COPY be/ .

# ── Frontend ──
COPY --from=fe-builder /build/fe/build /app/fe/build

# ── Config ──
COPY nginx/nginx.prod.conf /etc/nginx/nginx.conf
COPY supervisord.conf /etc/supervisord.conf

# /config/{cache,logs} — BE-generated covers and nginx access log.
# /data/{comics,videos,images,liked} — mount your actual media files here.
RUN mkdir -p \
      /config/cache/comics \
      /config/cache/videos \
      /config/cache/images \
      /config/logs \
      /config/db \
      /data/comics \
      /data/videos \
      /data/images \
      /data/liked \
      /run/nginx

ENV DB_PATH=/config/db/prod.sqlite \
    CACHE_PATH=/config/cache \
    LOG_PATH=/config/logs

EXPOSE 80

CMD ["supervisord", "-c", "/etc/supervisord.conf"]
