#!/bin/bash
#
# paperless-chandra deploy script for Unraid
# ============================================
# Run this from an Unraid terminal (Web UI > Terminal, or SSH).
#
# What it does:
#   1. Creates /mnt/user/appdata/paperless-chandra/
#   2. Clones the repo from GitHub
#   3. Writes your .env config (edit the 2 values below)
#   4. Builds the Docker image
#   5. Creates and starts the container
#

set -euo pipefail

# ============================================================
# EDIT THESE 2 VALUES — get from your Paperless-NGX settings
# and your Datalab dashboard
# ============================================================

PAPERLESS_API_TOKEN="YOUR_PAPERLESS_API_TOKEN"
DATALAB_API_KEY="YOUR_DATALAB_API_KEY"

# ============================================================
# You shouldn't need to change anything below
# ============================================================

APPDIR="/mnt/user/appdata/paperless-chandra"
REPO_DIR="$APPDIR/repo"
IMAGE_NAME="paperless-chandra:latest"
CONTAINER_NAME="paperless-chandra"
PAPERLESS_URL="http://192.168.1.145:8000"

echo "=== paperless-chandra deploy ==="

# Step 1: Create appdata directory
echo "[1/5] Creating $APPDIR ..."
mkdir -p "$APPDIR"

# Step 2: Clone the repo (or update if already exists)
if [ -d "$REPO_DIR/.git" ]; then
    echo "[2/5] Updating existing repo ..."
    cd "$REPO_DIR"
    git pull
else
    echo "[2/5] Cloning repo ..."
    git clone https://github.com/chirimoyas/paperless-chandra.git "$REPO_DIR"
fi

cd "$REPO_DIR"

# Step 3: Write .env file
echo "[3/5] Writing .env config ..."
cat > "$APPDIR/.env" <<EOF
PAPERLESS_BASE_URL=${PAPERLESS_URL}
PAPERLESS_API_TOKEN=${PAPERLESS_API_TOKEN}
CHANDRA_BACKEND=datalab
CHANDRA_BASE_URL=https://www.datalab.to
CHANDRA_API_KEY=${DATALAB_API_KEY}
POLL_INTERVAL=60
TAG_CHANDRA_OCR=chandra-ocr
PROCESSED_TAG=chandra-processed
SKIP_NATIVE_TEXT_PDFS=true
DRY_RUN=false
LOG_LEVEL=INFO
EOF

# Step 4: Build Docker image
echo "[4/5] Building Docker image (this takes a few minutes) ..."
docker build -t "$IMAGE_NAME" "$REPO_DIR"

# Step 5: Create and start container
echo "[5/5] Creating container ..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

docker run -d \
    --name "$CONTAINER_NAME" \
    --restart=unless-stopped \
    --env-file "$APPDIR/.env" \
    -v "$APPDIR:/config" \
    "$IMAGE_NAME"

echo ""
echo "=== Deploy complete ==="
echo ""
echo "Container status:"
docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
echo ""
echo "Logs (last 20 lines):"
docker logs --tail 20 "$CONTAINER_NAME" 2>&1 || true
echo ""
echo "To view live logs:   docker logs -f $CONTAINER_NAME"
echo "To stop:             docker stop $CONTAINER_NAME"
echo "To restart:          docker restart $CONTAINER_NAME"
echo "To dry-run once:     docker exec $CONTAINER_NAME python -m chandra_paperless --dry-run --once"
echo ""
echo "IMPORTANT: Create a 'chandra-ocr' tag in Paperless-NGX and tag"
echo "documents you want re-OCR'd. The script will pick them up automatically."