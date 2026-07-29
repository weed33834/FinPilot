# FinPilot 前端 — 多阶段构建（node 构建 + nginx 托管 SPA）
# 产物：nginx 容器，静态托管 dist/，并把 /api /ws 反向代理到 backend:8001

# ───────── Stage 1: 构建 ─────────
FROM node:20-alpine AS builder
WORKDIR /app

# 先复制依赖清单，利用 Docker 层缓存
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

# 再复制源码构建（vite build 产物到 dist/）
COPY . .
# 构建时注入后端地址；容器内通过 nginx 反代，前端无需感知后端真实端口
ENV VITE_API_BASE_URL=/api/v1
RUN npm run build

# ───────── Stage 2: 运行 ─────────
FROM nginx:1.27-alpine
# 替换默认配置为 SPA + 反代配置
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
# 拷贝构建产物到 nginx 静态目录
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
# nginx 默认即前台运行（daemon off），无需覆写 CMD
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget --spider -q http://localhost/ || exit 1
