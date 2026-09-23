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

# Bake fresh data snapshots into the image (NOT /data — the volume hides
# anything baked there). Render's free tier sleeps the container and /data
# is ephemeral, so without these the API serves scan_unavailable /
# thetahedge_unavailable for minutes after every cold boot while the
# background collectors run. The entrypoint copies these into /data when
# missing; the workers overwrite them with fresh data within minutes.
# Best-effort: a failed seed must never fail the build.
RUN mkdir -p /app/seed && \
    (cd /app/options-seller && \
     PYTHONPATH=/app/options-seller/src SCANNER_JSON_PATH=/app/seed/scan-latest.json \
     timeout 600 python -c "from api.collect_scan import collect; collect(); print('scan seed ok')" \
     || echo "scan seed skipped") && \
    (cd /app/options-seller && \
     PYTHONPATH=/app/options-seller/src PULSE_DATA_DIR=/app/seed \
     timeout 900 python -c "from api.thetahedge import collect; e=collect(); print('theta seed ok', e['total'])" \
     || echo "theta seed skipped") && \
    (cd /app/options-seller && \
     PYTHONPATH=/app/options-seller/src PULSE_DATA_DIR=/app/seed \
     timeout 1200 python -c "from api.breaches import collect; e=collect(); print('breaches seed ok', e['total'])" \
     || echo "breaches seed skipped") && \
    ls -la /app/seed/ || true

EXPOSE 8504

ENTRYPOINT ["/app/docker-entrypoint.sh"]
