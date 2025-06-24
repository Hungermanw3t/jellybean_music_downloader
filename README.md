# Jellybean Music Downloader

A web interface for downloading music from Qobuz via squid.wtf proxy with automatic MusicBrainz tagging.

## Features

- 🎵 Web-based album search and download
- 🖼️ Modern UI with album artwork
- 🏷️ Automatic MusicBrainz metadata tagging
- 📦 Docker deployment
- 🚀 No Qobuz API keys required

## Quick Start

### Prerequisites
- Docker and Docker Compose

### Deployment

1. **Clone and configure:**
   ```bash
   git clone <repo-url>
   cd jellybean_music_downloader
   cp .env.example .env
   # Edit .env for your configuration
   ```

2. **Deploy:**
   ```bash
   docker-compose up -d
   ```

3. **Access:**
   Open http://localhost:5000

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `HOST_DOWNLOADS_DIR` | Download directory on host | `./downloads` |
| `HOST_PORT` | Port mapping | `5000` |
| `FLASK_ENV` | Flask environment | `production` |
| `LOGIN_PASSWORD` | Web interface password | `1234` |

### Examples

**Development:**
```bash
export HOST_DOWNLOADS_DIR=./downloads
export FLASK_DEBUG=1
docker-compose up
```

**Production:**
```bash
export HOST_DOWNLOADS_DIR=/data/music
export HOST_PORT=80
export LOGIN_PASSWORD=secure_password
docker-compose up -d
```

## Usage

1. Access web interface
2. Search for albums
3. Select MusicBrainz release for tagging
4. Download with automatic metadata

## Security

- Change default login password
- Run behind reverse proxy for HTTPS
- Limit network access if needed
