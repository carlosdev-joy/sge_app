#!/bin/bash
# =============================================================
# gerar-cert.sh — Gera certificado SSL autoassinado para o nginx
#
# Uso:
#   bash scripts/gerar-cert.sh
#
# Gera em certs/:
#   orquestra.key  — chave privada RSA 2048 (nunca commitar)
#   orquestra.crt  — certificado autoassinado, validade 10 anos
# =============================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CERTS_DIR="$REPO_DIR/certs"
HOSTNAME="${1:-$(hostname)}"

mkdir -p "$CERTS_DIR"

echo ""
echo "Gerando certificado autoassinado para: $HOSTNAME"
echo ""

openssl req -x509 -nodes -days 3650 \
  -newkey rsa:2048 \
  -keyout "$CERTS_DIR/orquestra.key" \
  -out    "$CERTS_DIR/orquestra.crt" \
  -subj   "/CN=$HOSTNAME/O=ORQUESTRA/C=BR" \
  -addext "subjectAltName=DNS:$HOSTNAME,DNS:localhost,IP:127.0.0.1"

chmod 600 "$CERTS_DIR/orquestra.key"
chmod 644 "$CERTS_DIR/orquestra.crt"

echo ""
echo "✓ Certificado gerado em $CERTS_DIR/"
echo "  orquestra.crt  (certificado — válido por 10 anos)"
echo "  orquestra.key  (chave privada — não commitar!)"
echo ""
echo "Para instalar o certificado nos navegadores da rede corporativa"
echo "(evitar aviso de segurança), distribua o arquivo orquestra.crt"
echo "e instale como 'Autoridade Confiável' em cada máquina, ou via GPO."
echo ""
