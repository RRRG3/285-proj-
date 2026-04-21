FROM python:3.11-slim AS base

LABEL org.opencontainers.image.title="Quantum Portfolio Lab"
LABEL org.opencontainers.image.description="Enterprise-grade stock portfolio suggestion engine"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p logs data

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

ENV QPL_DEMO_MODE=0 \
    QPL_DEBUG=0 \
    QPL_PORT=8080

CMD ["python", "app.py"]
