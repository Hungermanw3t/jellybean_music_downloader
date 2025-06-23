# Qobuz Squid Downloader

A modern web interface for downloading music from Qobuz via squid.wtf proxy with automatic MusicBrainz tagging.

## Features

- 🎵 Web-based album and track search (via squid.wtf)
- 🖼️ Beautiful, modern UI with album artwork
- 🏷️ Automatic MusicBrainz metadata tagging
- 📦 Docker support for easy deployment
- 🔄 Progress tracking with loading screens
- 🎨 Hover overlays with album information
- 🚀 No Qobuz API keys required (uses squid.wtf proxy)

## Quick Start with Docker

### Prerequisites

- Docker and Docker Compose
- No API keys needed!

### Deployment

1. **Clone the repository:**
   ```bash
   git clone https://your-repo-url/jellybean_music_downloader.git
   cd jellybean_music_downloader
   ```

2. **Configure environment (optional):**
   ```bash
   cp .env.example .env
   # Edit .env if you want to customize settings
   ```

3. **Run with Docker Compose:**
   ```bash
   docker-compose -f docker-compose.production.yml up -d
   ```

4. **Access the web interface:**
   Open http://your-server-ip:5000

## Portainer Deployment

### Method 1: Using Portainer Stacks

1. **In Portainer:**
   - Go to "Stacks" → "Add Stack"
   - Name: `qobuz-downloader`
   - Build method: "Repository"
   - Repository URL: `https://github.com/yourusername/jellybean_music_downloader`
   - Compose path: `docker-compose.production.yml`

2. **Environment Variables (optional):**
   ```
   FLASK_SECRET_KEY=your-random-secret-key-here
   ```

3. **Deploy the stack**

### Method 2: Using Docker Compose Upload

1. **In Portainer:**
   - Go to "Stacks" → "Add Stack"
   - Name: `qobuz-downloader`
   - Build method: "Upload"
   - Upload your `docker-compose.production.yml`

2. **Configure volumes:**
   - Downloads will be saved to `./downloads` on your host

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FLASK_SECRET_KEY` | Flask session secret (generate random string) | Auto-generated |
| `DOWNLOAD_BASE_DIR` | Download directory inside container | `/app/downloads` |
| `FLASK_ENV` | Flask environment | `production` |
| `MUSICBRAINZ_USER_AGENT` | User agent for MusicBrainz API | Auto-set |

### Volume Mounts

- `./downloads:/app/downloads` - Downloaded music files

## How It Works

This application uses squid.wtf as a proxy to access Qobuz, so you don't need any Qobuz API credentials. It:

1. Searches for music via squid.wtf
2. Downloads tracks/albums through the proxy
3. Automatically tags files with MusicBrainz metadata
4. Saves organized music files to your downloads folder

## Health Checks

The container includes health checks that verify the web service is running:
- Check interval: 30 seconds
- Timeout: 10 seconds
- Retries: 3

## Updating

To update the application:

```bash
# Pull latest changes
git pull origin main

# Rebuild and restart
docker-compose -f docker-compose.production.yml down
docker-compose -f docker-compose.production.yml up -d --build
```

## Security Considerations

- Change default Flask secret key
- Use strong Qobuz credentials
- Consider running behind a reverse proxy (nginx/traefik)
- Limit network access if needed
- Regular backups of downloaded music

## Troubleshooting

### Container won't start:
```bash
docker-compose -f docker-compose.production.yml logs qobuz-downloader
```

### Web interface not accessible:
- Check if port 5000 is open on your server
- Verify firewall settings
- Check container status: `docker ps`

### Download issues:
- Verify Qobuz credentials
- Check download directory permissions
- Monitor container logs

## License

This project is for educational purposes only. Respect copyright laws and Qobuz's terms of service.
