FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y \
    wget curl gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser dependencies and Firefox
RUN playwright install-deps firefox
RUN playwright install firefox

RUN mkdir -p /app/data

COPY . .

CMD ["python", "main.py"]
