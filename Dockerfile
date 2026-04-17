FROM python:3.10-slim

WORKDIR /app

# Prevent Python from buffering stdout/stderr natively
ENV PYTHONUNBUFFERED=1

# Install dependencies exclusively
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core system architecture natively
COPY . .

# Expose API port (only strictly used by the API container)
EXPOSE 8000
