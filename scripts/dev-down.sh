#!/usr/bin/env bash
# dev-down.sh — Para o ambiente de desenvolvimento (mantém volumes/dados)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env.dev"

cd "$PROJECT_DIR"
[ -f "$ENV_FILE" ] && { set -a; source "$ENV_FILE"; set +a; }

echo "Parando ambiente de dev..."
docker compose \
    -f docker-compose.yaml \
    -f docker-compose.dev.yaml \
    --env-file "$ENV_FILE" \
    down

echo "Ambiente de dev parado. Volumes preservados."
echo "Para remover volumes também: docker compose ... down -v"
