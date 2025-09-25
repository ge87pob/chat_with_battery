#!/usr/bin/env bash
set -euo pipefail

# Non-interactive setup for ElevenLabs ConvAI projects
# - Installs convai CLI globally if missing
# - Initializes a convai project
# - Logs in using ELEVENLABS_API_KEY if provided
# - Creates a basic agent and syncs

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    return 1
  fi
}

# Check Node and npm
require_cmd node || { echo "Please install Node.js >= 16"; exit 1; }
require_cmd npm || { echo "Please install npm >= 8"; exit 1; }

# Install convai CLI if missing
if ! command -v convai >/dev/null 2>&1; then
  echo "Installing @elevenlabs/convai-cli globally..."
  npm install -g @elevenlabs/convai-cli --yes || npm install -g @elevenlabs/convai-cli
fi

# Initialize project if not already
if [ ! -f "convai.json" ] && [ ! -d ".convai" ]; then
  echo "Initializing ConvAI project..."
  yes "" | convai init || convai init --yes || true
fi

# Login if API key provided
if [ -n "${ELEVENLABS_API_KEY:-}" ]; then
  echo "Logging into ElevenLabs with provided API key (non-interactive)..."
  echo "$ELEVENLABS_API_KEY" | convai login --api-key-stdin || true
else
  echo "ELEVENLABS_API_KEY not set. You can export it and rerun for non-interactive login."
fi

# Add a default agent if none exists
if ! convai list agents 2>/dev/null | grep -q "My Assistant"; then
  echo "Creating default agent 'My Assistant' from assistant template..."
  convai add agent "My Assistant" --template assistant || true
fi

# Sync config to ElevenLabs
echo "Syncing configuration to ElevenLabs..."
convai sync || true

echo "Done. You can now customize your agent configuration under $REPO_DIR."
