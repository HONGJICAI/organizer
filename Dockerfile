# ── Stage 1: build SvelteKit static site ──────────────────────────────────────
FROM node:lts-alpine AS fe-builder
WORKDIR /build/fe
COPY fe/package*.json ./
RUN npm pkg delete scripts.prepare && npm ci
COPY fe/ ./
# Hide the "try demo (mock data)" button in the self-hosted image.
ENV VITE_HIDE_MOCK=1
RUN npm run build

# ── Stage 2: production runtime ───────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.13-alpine

RUN apk add --no-cache nginx supervisor

# ── RAR support ──
# rarfile shells out to a decompressor, and Alpine packages none that fully
# decodes RAR: its 7zip is built without the RAR codec, unrar/unar aren't
# packaged, and bsdtar fails on solid archives. Install the official static
# 7-Zip build as `7zz`, which rarfile picks up. BusyBox tar can't unpack the
# release (xz with the x86 BCJ filter), so real xz is fetched just for that.
ARG TARGETARCH
ARG SEVENZIP_VERSION=26.04
RUN set -eu; \
    case "${TARGETARCH:-amd64}" in \
      amd64) arch=x64;   sum=fc0327ba27e89bd086cf426dff17d77de582953cdbbc10a6576540a06853ffcd ;; \
      arm64) arch=arm64; sum=5b0ac3aa91c1e3499f011d6af69d7f6b4de3ef2f011d9e2ff44c58ebd04aa388 ;; \
      *) echo "No 7-Zip build configured for ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    apk add --no-cache --virtual .sevenzip-fetch xz; \
    wget -qO /tmp/7z.tar.xz "https://github.com/ip7z/7zip/releases/download/${SEVENZIP_VERSION}/7z$(echo "$SEVENZIP_VERSION" | tr -d .)-linux-${arch}.tar.xz"; \
    echo "${sum}  /tmp/7z.tar.xz" | sha256sum -c -; \
    xz -dc /tmp/7z.tar.xz | tar -x -C /tmp 7zzs; \
    install -m 755 /tmp/7zzs /usr/local/bin/7zz; \
    rm /tmp/7z.tar.xz /tmp/7zzs; \
    apk del .sevenzip-fetch; \
    7zz i | grep -q Rar5

# ── Backend ──
WORKDIR /app/be
COPY be/pyproject.toml be/uv.lock ./
# Install the exact versions from uv.lock (what CI tests), not whatever
# pyproject's lower bounds resolve to at build time.
RUN apk add --no-cache gcc python3-dev musl-dev linux-headers && \
    uv export --frozen --no-dev --no-hashes --no-emit-project -o /tmp/requirements.txt && \
    uv pip install --system --no-cache -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt
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
