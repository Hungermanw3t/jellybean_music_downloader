# Use an official Python image as the base
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_ENV=production

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install system dependencies for ffmpeg, wget, and curl (for health checks)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    wget \
    curl \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Download and install fpcalc (Chromaprint)
RUN wget -O /tmp/chromaprint.tar.gz https://github.com/acoustid/chromaprint/releases/download/v1.5.1/chromaprint-fpcalc-1.5.1-linux-x86_64.tar.gz && \
    tar -xzf /tmp/chromaprint.tar.gz -C /tmp && \
    mv /tmp/chromaprint-fpcalc-1.5.1-linux-x86_64/fpcalc /usr/local/bin/fpcalc && \
    chmod +x /usr/local/bin/fpcalc && \
    rm -rf /tmp/chromaprint*

# Copy requirements first for better Docker cache usage
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . /app

# Create downloads directory and set permissions
RUN mkdir -p /app/downloads && \
    chown -R appuser:appuser /app

# Expose a volume for downloads
VOLUME ["/app/downloads"]

# Expose the Flask app port
EXPOSE 5000

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Set the default command to run your app
CMD ["python", "webapp.py"]