#!/usr/bin/env bash
# Rebuild + restart the deriva-mcp-test container in a deriva-docker
# deployment, picking up new DERIVA_MCP_EXTRA_PACKAGES versions.
#
# Usage: ./scripts/rebuild-deriva-docker-mcp.sh [env-file]
# Default env file: ~/.deriva-docker/env/localhost.env
# Default deriva-docker compose dir: $DERIVA_DOCKER_DIR, falling back to
#   $HOME/GitHub/deriva-docker/deriva.

set -euo pipefail

ENV_FILE="${1:-$HOME/.deriva-docker/env/localhost.env}"
SERVICE="${DERIVA_MCP_SERVICE:-deriva-mcp-test}"
DERIVA_DOCKER_DIR="${DERIVA_DOCKER_DIR:-$HOME/GitHub/deriva-docker/deriva}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: env file not found at $ENV_FILE" >&2
    exit 1
fi
if [[ ! -f "$DERIVA_DOCKER_DIR/docker-compose.yml" ]]; then
    echo "Error: docker-compose.yml not found at $DERIVA_DOCKER_DIR" >&2
    echo "Set DERIVA_DOCKER_DIR to your deriva-docker checkout's compose dir." >&2
    exit 1
fi

cd "$DERIVA_DOCKER_DIR"
echo ">>> Working from: $DERIVA_DOCKER_DIR"
echo ">>> Stopping $SERVICE..."
docker-compose --env-file "$ENV_FILE" down "$SERVICE"
echo ">>> Rebuilding $SERVICE (--no-cache)..."
docker-compose --env-file "$ENV_FILE" build "$SERVICE" --no-cache
echo ">>> Starting $SERVICE..."
docker-compose --env-file "$ENV_FILE" up -d "$SERVICE"
echo ">>> Done. Tail logs with:"
echo "    docker-compose --env-file $ENV_FILE logs -f $SERVICE"
