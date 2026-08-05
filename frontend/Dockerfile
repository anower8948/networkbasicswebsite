# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Network Learning Platform — web image
#
# The React app is a static bundle; nginx serves it and reverse-proxies /api to
# the backend container, so the browser sees a single origin and the refresh
# cookie needs no cross-site exemption.
# ---------------------------------------------------------------------------

FROM node:22-alpine AS builder

WORKDIR /build

# Copy manifests first so `npm ci` is cached until dependencies actually change.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build


# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.inc /etc/nginx/conf.d/security-headers.inc

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
