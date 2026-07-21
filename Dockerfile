FROM python:3.12-slim

# Install Chromium for headless browser automation.
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code.
COPY . .

# Default command: show help.
CMD ["python", "main.py", "--help"]
