# Сборка SPA: зависимости ставятся отдельным слоем, чтобы правка кода не сбрасывала кеш npm.
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_MAILPIT_URL=http://localhost:8025
ARG VITE_SHOW_DEMO_ACCOUNTS=true
ENV VITE_MAILPIT_URL=$VITE_MAILPIT_URL \
    VITE_SHOW_DEMO_ACCOUNTS=$VITE_SHOW_DEMO_ACCOUNTS
RUN npm run build

# Раздача статики и проксирование /api на бэкенд: фронтенд и API на одном origin,
# поэтому refresh-cookie с SameSite=Strict работает без CORS.
FROM nginx:1.31-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD wget -qO- http://127.0.0.1/healthz || exit 1
