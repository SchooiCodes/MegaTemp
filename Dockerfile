FROM python:3.12-slim

# Install Chromium for headless browser automation.
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Tell pyppeteer to use the system Chromium instead of downloading its own
# (which fails in a minimal container) and keep its cache out of the image.
ENV PYPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV PYPPETEER_HOME=/tmp/pptr
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code.
COPY . .

# Default command: show help.
CMD ["python", "main.py", "--help"]
