#!/bin/bash
# =============================================================
# instalar-claude.sh — instala o Claude Code no servidor a partir
# da release do GitHub (mesmo canal de onde o deploy.sh já clona).
#
# Uso no servidor:
#   bash instalar-claude.sh [versão] [plataforma]
#   ex.: bash instalar-claude.sh 2.1.228 linux-x64
#
# Precisa alcançar github.com e objects.githubusercontent.com —
# atrás do proxy corporativo, exporte antes:
#   export HTTPS_PROXY=http://proxy.empresa:8080
# O curl abaixo herda essas variáveis sozinho.
#
# NÃO é chamado pelo deploy.sh: o Claude Code é ferramenta de
# operação, não artefato do produto, e uma falha aqui não pode
# derrubar o deploy do Orquestra.
# =============================================================
set -e

REPO="${REPO:-carlosdev-joy/sge_app}"
VERSAO="${1:-2.1.228}"
PLATAFORMA="${2:-linux-x64}"

# GITHUB_BASE existe para dois casos: testar o script contra um
# servidor local antes de publicar a release, e apontar para um
# mirror interno se um dia o github.com sair do allowlist.
GITHUB_BASE="${GITHUB_BASE:-https://github.com}"

TAG="claude-code-$VERSAO"
ARQ="claude-code-$VERSAO-$PLATAFORMA.tar.gz"
URL="$GITHUB_BASE/$REPO/releases/download/$TAG/$ARQ"

echo "[CLAUDE] baixando $ARQ da release $TAG"
if [ -n "${HTTPS_PROXY:-${https_proxy:-}}" ]; then
    echo "[CLAUDE] usando proxy: ${HTTPS_PROXY:-$https_proxy}"
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"

# --fail para que erro HTTP (404 de tag errada, bloqueio do proxy)
# vire falha do script, e não um arquivo HTML salvo como .tar.gz.
if ! curl -fSL --progress-bar -o "$ARQ" "$URL"; then
    echo "[CLAUDE] ERRO: download falhou." >&2
    echo "         Verifique: a tag '$TAG' existe na release? o proxy libera github.com" >&2
    echo "         e objects.githubusercontent.com?" >&2
    exit 1
fi
curl -fsSL -o "$ARQ.sha256" "$URL.sha256"

# O .sha256 foi gerado com o nome puro do arquivo, então basta
# conferir na pasta onde ele está.
sha256sum -c "$ARQ.sha256" \
  || { echo "[CLAUDE] ERRO: SHA256 não confere — download corrompido." >&2; exit 1; }
echo "[CLAUDE] ✓ pacote íntegro"

tar -xzf "$ARQ"
cd "claude-code-$VERSAO-$PLATAFORMA"

# Daqui em diante é o instalador offline do pacote: ele não baixa
# nada, confere plataforma/glibc/SHA256 e instala em ~/.local.
bash instalar.sh
