#!/bin/bash

# Fix permissions for downloads directory
# Run this script if you have permission issues with existing downloads

echo "Fixing permissions for downloads directory..."

# Get the current user's UID and GID
PUID=$(id -u)
PGID=$(id -g)

echo "Setting ownership to $PUID:$PGID"

# Fix ownership of downloads directory
sudo chown -R $PUID:$PGID ./downloads

# Make sure directories are readable/writable/executable
sudo find ./downloads -type d -exec chmod 755 {} \;

# Make sure files are readable/writable
sudo find ./downloads -type f -exec chmod 644 {} \;

echo "Permissions fixed!"
echo "You may need to rebuild and redeploy your Docker container for changes to take effect."
