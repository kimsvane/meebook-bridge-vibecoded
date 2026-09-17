FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

LABEL \
    io.hass.version="1.0.9" \
    io.hass.type="addon" \
    io.hass.arch="aarch64|amd64"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python3 -m playwright install chromium

COPY run.sh app.py ./
COPY custom_components /app/custom_components
RUN chmod a+x /app/run.sh \
    && mkdir -p /data

ENTRYPOINT []
CMD ["/app/run.sh"]