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
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code and default config ──────────────────────────────────────
COPY askloud/             ./askloud/
COPY askloud.py           .
COPY askloud_collector.py .
COPY config/              ./config/

# data/ and credentials are mounted at runtime — never baked in
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "askloud.py"]
