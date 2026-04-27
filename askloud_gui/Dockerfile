# Build context must be the repo root (cloud_inventory_claude/).
# docker build -f askloud_gui/Dockerfile .
#
# The image bundles:
#   - AWS CLI v2 / Azure CLI / Google Cloud CLI  (for live-query mode)
#   - The askloud engine package (Python)
#   - The Django GUI app

FROM python:3.12-slim

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl unzip ca-certificates gnupg \
    && rm -rf /var/lib/apt/lists/*

# ── AWS CLI v2 ────────────────────────────────────────────────────────────────
RUN curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/aws.zip \
    && unzip -q /tmp/aws.zip -d /tmp \
    && /tmp/aws/install \
    && rm -rf /tmp/aws.zip /tmp/aws

# ── Azure CLI ─────────────────────────────────────────────────────────────────
RUN curl -fsSL https://aka.ms/InstallAzureCLIDeb | bash \
    && rm -rf /var/lib/apt/lists/*

# ── Google Cloud CLI ──────────────────────────────────────────────────────────
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] \
        https://packages.cloud.google.com/apt cloud-sdk main" \
        > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
        | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y --no-install-recommends google-cloud-cli \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt            ./engine-requirements.txt
COPY askloud_gui/requirements.txt ./gui-requirements.txt
RUN pip install --no-cache-dir -r engine-requirements.txt -r gui-requirements.txt

# ── Askloud engine package ────────────────────────────────────────────────────
COPY askloud/             ./askloud/
COPY askloud.py           .
COPY askloud_collector.py .
COPY config/              ./config/

# ── Django GUI app ────────────────────────────────────────────────────────────
COPY askloud_gui/         ./askloud_gui/

# data/ is mounted at runtime — never baked in
RUN mkdir -p /app/data

# ── Static files ──────────────────────────────────────────────────────────────
# Collect into askloud_gui/staticfiles/ so whitenoise can serve them at runtime
# without DEBUG=True or a separate web server.
ENV DJANGO_SECRET_KEY=build-time-placeholder
RUN python askloud_gui/manage.py collectstatic --noinput
ENV DJANGO_SECRET_KEY=

# ── Runtime configuration ─────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/askloud_gui
ENV ASKLOUD_BASE_DIR=/app
ENV DJANGO_DEBUG=false

EXPOSE 8000

CMD ["gunicorn", "askloud_gui.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
