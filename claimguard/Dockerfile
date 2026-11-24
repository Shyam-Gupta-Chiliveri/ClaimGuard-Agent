FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LOKY_MAX_CPU_COUNT=2

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY core core
COPY pipeline pipeline
COPY ml ml
COPY rag rag
COPY app app
COPY configs configs
COPY data data
COPY web web

# MLOps inside the build: data contracts -> train -> quality gate -> anomaly model -> drift -> report.
# A failing contract or gate fails the image build.
RUN python -m pipeline.validate \
 && python -m ml.regionalklasse \
 && python -m ml.anomaly \
 && python -m ml.drift \
 && python -m pipeline.report

RUN useradd --uid 10001 --create-home claimguard && chown -R claimguard /app
USER claimguard

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
