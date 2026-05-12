FROM python:3.11-slim

WORKDIR /app

# 系统依赖（极简版：仅 curl 用于健康检查，pymupdf 自带 MuPDF）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 生产使用 gunicorn + uvicorn workers，支持多 worker 并行
# WORKERS 默认 2，可通过环境变量覆盖
ENV WORKERS=2
CMD ["sh", "-c", "gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --workers ${WORKERS} --timeout 120 --graceful-timeout 30 --access-logfile -"]
