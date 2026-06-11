FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y \
    wget curl gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install firefox --with-deps

COPY . .

# Run as non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python", "main.py"]
