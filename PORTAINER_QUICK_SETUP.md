# Quick Portainer Setup Guide

## Step 1: Prepare Your Environment

1. **Find your user ID and group ID:**
   ```bash
   id
   # Output: uid=1000(username) gid=1000(groupname) groups=...
   # Use the uid and gid numbers for PUID and PGID
   ```

2. **Choose your download directory:**
   - `/home/user/music` (home directory)
   - `/data/music` (dedicated data directory)
   - `/mnt/nas/music` (NAS mount)

3. **Create the directory and set permissions:**
   ```bash
   sudo mkdir -p /home/user/music
   sudo chown 1000:1000 /home/user/music
   ```

## Step 2: Deploy in Portainer

### Method 1: Using Environment Variables (Recommended)

1. **In Portainer → Stacks → Add Stack:**
   - **Name:** `qobuz-downloader`
   - **Build method:** Git Repository
   - **Repository URL:** `https://github.com/yourusername/jellybean_music_downloader`
   - **Compose path:** `docker-compose.yml`

2. **Copy these Environment Variables:**
   ```
   HOST_DOWNLOADS_DIR=/home/user/music
   HOST_PORT=5000
   LOGIN_PASSWORD=your_secure_password_here
   FLASK_SECRET_KEY=random_secret_key_generate_this
   PUID=1000
   PGID=1000
   FLASK_ENV=production
   FLASK_DEBUG=0
   RESTART_POLICY=unless-stopped
   HEALTHCHECK_DISABLE=false
   ```

3. **Deploy the stack**

### Method 2: Using .env File Upload

1. **Download `.env.portainer` file**
2. **Edit the values for your setup**
3. **In Portainer → Stacks → Add Stack:**
   - **Name:** `qobuz-downloader`
   - **Build method:** Upload
   - **Upload:** Your edited docker-compose.yml and .env file

## Step 3: Access Your Downloader

1. **Wait for deployment to complete**
2. **Check container logs if needed:**
   - Go to Containers → qobuz-downloader → Logs
3. **Access web interface:**
   - URL: `http://your-server-ip:5000`
   - Login with your password

## Common Environment Variables

| Variable | Required | Example | Description |
|----------|----------|---------|-------------|
| `HOST_DOWNLOADS_DIR` | **Yes** | `/home/user/music` | Where files are saved |
| `LOGIN_PASSWORD` | **Yes** | `my_secure_password` | Web login password |
| `PUID` | **Yes** | `1000` | User ID for permissions |
| `PGID` | **Yes** | `1000` | Group ID for permissions |
| `HOST_PORT` | No | `5000` | Web interface port |
| `FLASK_SECRET_KEY` | Recommended | `random_string` | Session security |

## Troubleshooting

### Downloads not appearing:
1. Check `HOST_DOWNLOADS_DIR` path exists
2. Verify permissions: `ls -la /path/to/downloads`
3. Check PUID/PGID match your user

### Can't access web interface:
1. Check HOST_PORT is not in use
2. Verify firewall allows the port
3. Use server IP, not localhost

### Permission errors:
```bash
# Fix permissions
sudo chown -R 1000:1000 /path/to/downloads
sudo chmod -R 755 /path/to/downloads
```

## Security Notes

- Always change the default login password
- Use a random Flask secret key
- Consider using a reverse proxy for HTTPS
- Limit network access if possible
