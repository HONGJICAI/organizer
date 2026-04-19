# ── Stage 1: build SvelteKit static site ──────────────────────────────────────
FROM node:22-alpine AS fe-builder
WORKDIR /build/fe
COPY fe/package*.json ./
RUN npm ci
COPY fe/ ./
RUN npm run build

# ── Stage 2: production runtime ───────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.13-alpine

RUN apk add --no-cache nginx supervisor

# ── Backend ──
WORKDIR /app/be
COPY be/pyproject.toml be/uv.lock ./
RUN uv pip install --system --no-cache -r pyproject.toml
COPY be/ .

# ── Frontend ──
COPY --from=fe-builder /build/fe/build /app/fe/build

# ── Config ──
COPY nginx/nginx.prod.conf /etc/nginx/http.d/default.conf
COPY supervisord.conf /etc/supervisord.conf

# Directories the BE and nginx expect at runtime.
# /app/nginx/html/{comics,videos,images} — BE symlinks media here; nginx serves from here.
# /app/nginx/logs                        — nginx writes access log; BE reads it for cache stats.
# /data/{comics,videos,images}           — mount your actual media files here.
RUN mkdir -p \
      /app/nginx/html/comics \
      /app/nginx/html/videos \
      /app/nginx/html/images \
      /app/nginx/logs \
      /data/comics \
      /data/videos \
      /data/images \
      /data/db \
      /run/nginx

ENV DB_PATH=/data/db/organizer.db

EXPOSE 80

CMD ["supervisord", "-c", "/etc/supervisord.conf"]
