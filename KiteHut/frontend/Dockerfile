# ============================================================
# RepoLens Frontend — Production Image
# Stage 1: build the React app with Vite
# Stage 2: serve static files with Nginx (which proxies /api)
# ============================================================

# ---------- Build stage ----------
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---------- Serve stage ----------
FROM nginx:1.27-alpine

# API proxy + SPA fallback configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]