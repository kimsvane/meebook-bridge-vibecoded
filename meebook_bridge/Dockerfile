FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

LABEL \
    io.hass.version="1.0.3" \
    io.hass.type="addon" \
    io.hass.arch="aarch64|amd64"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY run.sh app.py ./
RUN chmod a+x /app/run.sh \
    && mkdir -p /data

ENV DISPLAY=:99
ENTRYPOINT []
CMD ["/app/run.sh"]