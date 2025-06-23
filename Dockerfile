# Use an official Python image as the base
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_ENV=production

WORKDIR /app

# Install system dependencies for ffmpeg, wget, curl, and gosu for user management
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    wget \
    curl \
    ca-certificates \
    gosu && \
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

# Create downloads directory
RUN mkdir -p /app/downloads

# Expose a volume for downloads
VOLUME ["/app/downloads"]

# Expose the Flask app port
EXPOSE 5000

# Create entrypoint script to handle user permissions
RUN echo '#!/bin/bash\n\
PUID=${PUID:-1000}\n\
PGID=${PGID:-1000}\n\
\n\
# Create group and user with specified IDs\n\
groupadd -g $PGID appuser 2>/dev/null || true\n\
useradd -u $PUID -g $PGID -s /bin/bash appuser 2>/dev/null || true\n\
\n\
# Ensure downloads directory has correct ownership\n\
chown -R $PUID:$PGID /app/downloads\n\
\n\
# Execute the main command as the appuser\n\
exec gosu appuser "$@"\n\
' > /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Set the default command to run your app
CMD ["python", "webapp.py"]