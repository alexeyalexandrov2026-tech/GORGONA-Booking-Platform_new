FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

RUN apt-get update \
    && apt-get install -y --no-install-recommends clamav clamav-daemon ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/run/clamav /var/lib/clamav /app \
    && chown -R clamav:clamav /var/run/clamav /var/lib/clamav \
    && freshclam --quiet || true

COPY clamd.conf /etc/clamav/clamd.conf
COPY server.py /app/server.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

WORKDIR /app
EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
