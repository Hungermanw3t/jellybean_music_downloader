# Portainer Deployment Guide

## Quick Setup

### Method 1: Using Portainer Stacks (Recommended)

1. **In Portainer, go to Stacks → Add Stack**

2. **Stack Configuration:**
   - **Name:** `qobuz-downloader`
   - **Build method:** Choose "Git Repository" or "Upload"

3. **If using Git Repository:**
   - **Repository URL:** `https://github.com/yourusername/jellybean_music_downloader`
   - **Reference:** `refs/heads/main`
   - **Compose path:** `docker-compose.yml`

4. **Environment Variables (set these in Portainer):**
   ```
   HOST_DOWNLOADS_DIR=/data/downloads
   HOST_PORT=5000
   LOGIN_PASSWORD=your_secure_password
   PUID=1000
   PGID=1000
   FLASK_ENV=production
   RESTART_POLICY=unless-stopped
   ```

5. **Deploy the stack**

### Method 2: Upload Docker Compose

1. **Download/copy the `docker-compose.yml` file**

2. **In Portainer:**
   - Go to Stacks → Add Stack
   - Name: `qobuz-downloader`
   - Build method: "Upload"
   - Upload your `docker-compose.yml`

3. **Set Environment Variables** (see examples below)

4. **Deploy**

## Download Directory Configuration

### Option A: Host Directory (Recommended)
Map downloads to a directory on your Docker host:

```env
HOST_DOWNLOADS_DIR=/home/user/music
```

### Option B: Docker Volume
Use a Docker volume (managed by Docker):

```env
HOST_DOWNLOADS_DIR=qobuz_music
```

### Option C: NAS/Network Storage
Map to network-attached storage:

```env
HOST_DOWNLOADS_DIR=/mnt/nas/music
```

## Important Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `HOST_DOWNLOADS_DIR` | **Download location** | `/data/music` |
| `LOGIN_PASSWORD` | **Web interface password** | `my_secure_password` |
| `HOST_PORT` | Port to access web interface | `5000` |
| `PUID` | User ID for file permissions | `1000` |
| `PGID` | Group ID for file permissions | `1000` |

## Step-by-Step Portainer Setup

### 1. Find Your User ID (for file permissions)
On your Docker host, run:
```bash
id $(whoami)
```
This shows your `PUID` and `PGID` (usually 1000).

### 2. Choose Download Directory
Decide where you want music downloaded:
- `/home/user/Downloads/Music`
- `/data/music`
- `/mnt/storage/music`

### 3. Create Portainer Stack

**Environment Variables in Portainer:**
```
HOST_DOWNLOADS_DIR=/home/user/Downloads/Music
HOST_PORT=5000
LOGIN_PASSWORD=secure_password_here
PUID=1000
PGID=1000
FLASK_ENV=production
FLASK_DEBUG=0
RESTART_POLICY=unless-stopped
HEALTHCHECK_DISABLE=false
```

### 4. Deploy and Access

1. **Deploy the stack**
2. **Wait for container to start** (check logs if issues)
3. **Access:** `http://your-server-ip:5000`
4. **Login** with your password
5. **Test download** to verify files appear in your chosen directory

## Troubleshooting

### Downloads not appearing in expected directory:
1. Check Portainer stack environment variables
2. Verify host directory exists and has correct permissions:
   ```bash
   sudo mkdir -p /your/download/path
   sudo chown 1000:1000 /your/download/path
   ```

### Permission denied errors:
1. Check PUID/PGID match your user:
   ```bash
   id $(whoami)
   ```
2. Update environment variables in Portainer stack
3. Redeploy stack

### Container won't start:
1. Check Portainer logs for the container
2. Verify all required environment variables are set
3. Ensure no port conflicts (change HOST_PORT if needed)

### Can't access web interface:
1. Check HOST_PORT environment variable
2. Verify port is not blocked by firewall
3. Use server IP address, not localhost

## Example Portainer Environment Variables

**For home server (downloads to /home/user/music):**
```
HOST_DOWNLOADS_DIR=/home/user/music
HOST_PORT=5000
LOGIN_PASSWORD=my_password_123
PUID=1000
PGID=1000
```

**For NAS setup (downloads to mounted NAS):**
```
HOST_DOWNLOADS_DIR=/mnt/nas/media/music
HOST_PORT=8080
LOGIN_PASSWORD=nas_music_downloader
PUID=1001
PGID=1001
```

**For Docker volume (Docker manages storage):**
```
HOST_DOWNLOADS_DIR=music_downloads
HOST_PORT=5000
LOGIN_PASSWORD=volume_managed
PUID=1000
PGID=1000
```

## Security Notes

- Always change the default login password
- Consider running behind a reverse proxy for HTTPS
- Limit access to trusted networks if possible
- Regular backups of downloaded music
