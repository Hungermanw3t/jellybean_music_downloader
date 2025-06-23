# Use an official Python image as the base
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install system dependencies for ffmpeg and wget
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg wget ca-certificates && \
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

# Expose a volume for downloads (optional, for clarity)
VOLUME ["/app/downloads"]

# Expose the Flask app port
EXPOSE 5000

# Set the default command to run your app
CMD ["python", "webapp.py"]