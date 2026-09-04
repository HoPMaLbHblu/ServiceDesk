# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS deps
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund

# Development: Vite dev server with hot reload; source is bind-mounted.
FROM deps AS dev
COPY frontend/ ./
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]

FROM deps AS build
COPY frontend/ ./
RUN npm run build

# Production: nginx serves the built SPA and proxies the API to Django.
FROM nginx:1.27-alpine AS prod
COPY infrastructure/nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
