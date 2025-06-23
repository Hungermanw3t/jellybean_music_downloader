#!/bin/bash

# Qobuz Squid Downloader Deployment Script
# Usage: ./deploy.sh

set -e

echo "🎵 Qobuz Squid Downloader - Simple Deployment"
echo "============================================"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create downloads directory
echo "📁 Creating downloads directory..."
mkdir -p downloads

# Copy environment file if it doesn't exist (optional)
if [ ! -f .env ]; then
    echo "⚙️ Creating environment file (optional customization)..."
    cp .env.example .env
    echo "✏️ Environment file created. Edit .env if you want to customize settings."
    echo "   (Flask secret key will be auto-generated if not set)"
fi

# Build and start the application
echo "🐳 Building and starting Docker containers..."
docker-compose -f docker-compose.production.yml up -d --build

# Wait for the application to start
echo "⏳ Waiting for application to start..."
sleep 15

# Check if the application is running
if curl -f http://localhost:5000 &> /dev/null; then
    echo "✅ Application is running successfully!"
    echo "🌐 Access your Qobuz Downloader at: http://$(hostname -I | awk '{print $1}'):5000"
    echo ""
    echo "📋 Useful commands:"
    echo "   View logs:     docker-compose -f docker-compose.production.yml logs -f"
    echo "   Stop:          docker-compose -f docker-compose.production.yml down"
    echo "   Restart:       docker-compose -f docker-compose.production.yml restart"
    echo "   Update:        git pull && docker-compose -f docker-compose.production.yml up -d --build"
    echo ""
    echo "📁 Downloads will be saved to: $(pwd)/downloads"
else
    echo "❌ Application failed to start. Check logs:"
    docker-compose -f docker-compose.production.yml logs
fi
