FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860 \
    TZ=Asia/Kolkata \
    DISABLE_SCHEDULER=0

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user

WORKDIR /app

COPY --chown=user:user mobile/requirements.txt ./mobile/requirements.txt
RUN pip install --no-cache-dir -r mobile/requirements.txt

COPY --chown=user:user . .
RUN mkdir -p /app/local_data && chown -R user:user /app

USER user

EXPOSE 7860

HEALTHCHECK --interval=45s --timeout=8s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:7860/api/health || exit 1

CMD ["uvicorn", "mobile.mobile_api:app", "--host", "0.0.0.0", "--port", "7860"]
