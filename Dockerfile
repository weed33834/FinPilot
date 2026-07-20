FROM python:3.13-slim

WORKDIR /app

# 安装系统依赖
# - build-essential: 编译 numpy<2 等需要
# - libfreetype6, libfontconfig1: matplotlib 字体渲染
# - libpq-dev: pg8000 编译需要
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential libfreetype6 libfontconfig1 libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（使用完整 requirements.txt，确保 langgraph / mcp / RAG 等模块可用）
COPY requirements.txt setup.py ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制源代码并以可编辑模式安装本包（让 finpilot 与 finpilot_equity 都可被 import）
COPY . .
RUN pip install --no-cache-dir -e . && \
    apt-get purge -y --auto-remove build-essential && \
    rm -rf /var/lib/apt/lists/*

EXPOSE 8001

# 默认启动 Web 应用入口（端口 8001）
# 可通过 docker run 覆盖 CMD 启动其他入口
CMD ["uvicorn", "finpilot_equity.web_app.main:app", "--host", "0.0.0.0", "--port", "8001"]
