#!/bin/bash
#
# Unraid template for paperless-chandra
# Place in /boot/config/plugins/dockerMan/templates-user/
# or use Unraid's "Add Container" > Template tab
#
# Required env vars:
#   PAPERLESS_BASE_URL   - e.g. http://192.168.1.145:8000
#   PAPERLESS_API_TOKEN  - Paperless API token
#   CHANDRA_API_KEY      - Datalab API key
#
# Optional env vars (defaults shown):
#   CHANDRA_BACKEND=datalab
#   CHANDRA_BASE_URL=https://www.datalab.to
#   POLL_INTERVAL=60
#   TAG_CHANDRA_OCR=chandra-ocr
#   PROCESSED_TAG=chandra-processed
#   DRY_RUN=false
#   ONCE=false
#   LOG_LEVEL=INFO
#   SKIP_NATIVE_TEXT_PDFS=true
#   MIN_PAGES=1
#   MAX_PAGES=0
#
# To build: docker build -t paperless-chandra .
# To run:   docker run -d --name paperless-chandra --env-file /config/paperless-chandra.env paperless-chandra
# To run once (batch mode): docker run --rm --env-file /config/paperless-chandra.env paperless-chandra --once