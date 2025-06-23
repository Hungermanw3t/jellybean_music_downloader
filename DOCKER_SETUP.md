# Docker Compose Configuration Guide

This project supports different configurations for development and production environments.

## Option 1: Using Override Files (Recommended)

### Development (Default)
```bash
# This automatically uses docker-compose.yml + docker-compose.override.yml
docker-compose up
```

### Production
```bash
# Use production configuration
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Option 2: Using Environment Variables

### Development
```bash
# Copy development environment
cp .env.development .env
docker-compose -f docker-compose.env.yml up
```

### Production
```bash
# Copy production environment
cp .env.production .env
docker-compose -f docker-compose.env.yml up -d
```

## Configuration Details

### Development Settings:
- Flask debug mode enabled
- Downloads to `./downloads` (local directory)
- Runs on port 5000
- No restart policy

### Production Settings:
- Flask debug mode disabled
- Downloads to `/data/music` (or custom path via HOST_DOWNLOADS_DIR)
- Runs on port 80
- Restart policy: unless-stopped

## Environment Variables

You can override any setting using environment variables:

```bash
# Custom downloads directory
export HOST_DOWNLOADS_DIR=/path/to/your/music
docker-compose up

# Custom port
export HOST_PORT=8080
docker-compose -f docker-compose.env.yml up
```

## Files Explanation

- `docker-compose.yml` - Base configuration
- `docker-compose.override.yml` - Development overrides (auto-loaded)
- `docker-compose.prod.yml` - Production overrides
- `docker-compose.env.yml` - Environment variable driven configuration
- `.env.development` - Development environment variables
- `.env.production` - Production environment variables
