# Pulse backend — FastAPI (options-seller/api) + Yahoo Finance market data.
#
# The iOS app talks to this at <host>/pulse (the /pulse prefix is stripped
# by middleware, so it also serves at /). No API keys needed.
#
# Build: docker build -t pulse-backend .
# Run:   docker run -p 8504:8504 pulse-backend
# Render: new Web Service -> Runtime Docker -> Dockerfile at repo root.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PULSE_DATA_DIR=/data \
    PULSE_SCAN_COLLECTOR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY options-seller/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Backend code. stock-data-scanner/ must sit next to options-seller/
# (api/main.py imports scanner modules from there via importlib).
COPY options-seller/ /app/options-seller/
COPY stock-data-scanner/ /app/stock-data-scanner/
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Runtime data (paper portfolio, caches). Seeded on first boot by entrypoint.
RUN mkdir -p /data
VOLUME /data

EXPOSE 8504

ENTRYPOINT ["/app/docker-entrypoint.sh"]
