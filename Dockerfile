FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y \
    wget curl gnupg \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user early
RUN useradd -m appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install system-level browser dependencies as root
RUN playwright install-deps firefox

# Install the Firefox browser binary as appuser so it lands in /home/appuser/.cache
USER appuser
RUN playwright install firefox

USER root
COPY . .
RUN chown -R appuser /app && mkdir -p /app/data && chown appuser /app/data

USER appuser

CMD ["python", "main.py"]
