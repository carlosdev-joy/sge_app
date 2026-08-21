#!/bin/bash
# =============================================================
# empacotar-claude-offline.sh — monta o pacote de instalação do
# Claude Code para servidor SEM internet.
#
# Roda numa máquina COM internet (esta VPS). Baixa o binário
# nativo, verifica a assinatura GPG do manifesto e o SHA256 do
# binário, e produz um .tar.gz auto-contido para transporte.
#
# Uso: bash empacotar-claude-offline.sh [plataforma] [versão]
#   plataforma: linux-x64 (padrão) | linux-arm64
#               | linux-x64-musl | linux-arm64-musl
#   versão:     stable (padrão) | latest | 2.1.238
#
# O pacote NÃO entra no git: o binário tem ~339 MB e o GitHub
# recusa arquivo acima de 100 MB.
# =============================================================
set -e

PLATAFORMA="${1:-linux-x64}"
ALVO="${2:-stable}"

BASE_URL="https://downloads.claude.ai/claude-code-releases"
CHAVE_URL="https://downloads.claude.ai/keys/claude-code.asc"
# Fingerprint da chave de release da Anthropic — publicada na documentação.
# Se este valor não bater com o da chave baixada, o pacote NÃO é montado.
FINGERPRINT="31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE"

AQUI="$(cd "$(dirname "$0")" && pwd)"
TRABALHO="$AQUI/trabalho"
DIST="$AQUI/dist"

echo "[EMPACOTA] plataforma=$PLATAFORMA alvo=$ALVO"

# ── 1. Resolver a versão ──────────────────────────────────────
# 'stable' e 'latest' são ponteiros; o pacote precisa de um número
# fixo para o servidor saber exatamente o que recebeu.
case "$ALVO" in
    stable|latest) VERSAO=$(curl -fsSL "$BASE_URL/$ALVO") ;;
    *)             VERSAO="$ALVO" ;;
esac
case "$VERSAO" in
    [0-9]*.[0-9]*.[0-9]*) : ;;
    *) echo "[EMPACOTA] ERRO: versão inesperada: '$VERSAO'" >&2; exit 1 ;;
esac
echo "[EMPACOTA] versão resolvida: $VERSAO"

PKG="$TRABALHO/claude-code-$VERSAO-$PLATAFORMA"
rm -rf "$PKG"; mkdir -p "$PKG" "$DIST"

# ── 2. Manifesto + assinatura + chave pública ─────────────────
curl -fsSL -o "$PKG/manifest.json"     "$BASE_URL/$VERSAO/manifest.json"
curl -fsSL -o "$PKG/manifest.json.sig" "$BASE_URL/$VERSAO/manifest.json.sig"
curl -fsSL -o "$PKG/claude-code.asc"   "$CHAVE_URL"

# ── 3. Verificar a assinatura do manifesto ────────────────────
# Keyring temporário e próprio: não mexe no chaveiro do usuário.
# Verificar a assinatura do manifesto verifica, por tabela, TODOS
# os binários que ele lista (cada um pelo seu SHA256).
GNUPG_TMP="$TRABALHO/gnupg"
rm -rf "$GNUPG_TMP"; mkdir -p -m 700 "$GNUPG_TMP"
gpg --homedir "$GNUPG_TMP" --batch --quiet --import "$PKG/claude-code.asc"

FP_LIDO=$(gpg --homedir "$GNUPG_TMP" --batch --with-colons --fingerprint \
          | awk -F: '/^fpr:/ {print $10; exit}')
if [ "$FP_LIDO" != "$FINGERPRINT" ]; then
    echo "[EMPACOTA] ERRO: fingerprint da chave não confere." >&2
    echo "           esperado: $FINGERPRINT" >&2
    echo "           recebido: $FP_LIDO" >&2
    exit 1
fi
echo "[EMPACOTA] ✓ chave de release confere ($FINGERPRINT)"

gpg --homedir "$GNUPG_TMP" --batch --verify \
    "$PKG/manifest.json.sig" "$PKG/manifest.json" 2>/dev/null \
  || { echo "[EMPACOTA] ERRO: assinatura do manifesto inválida." >&2; exit 1; }
echo "[EMPACOTA] ✓ assinatura do manifesto válida"

# ── 4. Checksum da plataforma escolhida ───────────────────────
# jq quando existe; senão, um recorte simples do JSON de uma linha.
if command -v jq >/dev/null 2>&1; then
    CHECKSUM=$(jq -r ".platforms[\"$PLATAFORMA\"].checksum // empty" "$PKG/manifest.json")
else
    CHECKSUM=$(tr -d '\n\r\t ' < "$PKG/manifest.json" \
               | grep -o "\"$PLATAFORMA\":{[^}]*}" \
               | grep -o '"checksum":"[a-f0-9]\{64\}"' \
               | cut -d'"' -f4)
fi
if [[ ! "$CHECKSUM" =~ ^[a-f0-9]{64}$ ]]; then
    echo "[EMPACOTA] ERRO: plataforma '$PLATAFORMA' não está no manifesto." >&2
    exit 1
fi

# ── 5. Baixar o binário e conferir ────────────────────────────
# Cache por versão+plataforma: remontar o pacote (mexer no instalador,
# no leia-me) não rebaixa 340 MB. O cache só é aceito quando o SHA256
# bate com o manifesto desta versão.
CACHE="$AQUI/cache/claude-$VERSAO-$PLATAFORMA"
mkdir -p "$AQUI/cache"
if [ -f "$CACHE" ] && [ "$(sha256sum "$CACHE" | cut -d' ' -f1)" = "$CHECKSUM" ]; then
    echo "[EMPACOTA] binário reaproveitado do cache"
    cp "$CACHE" "$PKG/claude"
else
    echo "[EMPACOTA] baixando o binário (~340 MB)..."
    curl -fSL --progress-bar -o "$PKG/claude" "$BASE_URL/$VERSAO/$PLATAFORMA/claude"
    cp "$PKG/claude" "$CACHE"
fi

REAL=$(sha256sum "$PKG/claude" | cut -d' ' -f1)
if [ "$REAL" != "$CHECKSUM" ]; then
    echo "[EMPACOTA] ERRO: SHA256 do binário não bate com o manifesto." >&2
    echo "           manifesto: $CHECKSUM" >&2
    echo "           baixado:   $REAL" >&2
    exit 1
fi
chmod +x "$PKG/claude"
echo "[EMPACOTA] ✓ SHA256 do binário confere"

# ── 6. Instalador e leia-me viajam junto ──────────────────────
cp "$AQUI/instalar.sh" "$PKG/instalar.sh"
cp "$AQUI/LEIAME.md"   "$PKG/LEIAME.md"
chmod +x "$PKG/instalar.sh"

# Ficha do pacote: o instalador lê daqui e não precisa de jq nem
# de parser de JSON no servidor.
{
    echo "VERSAO=$VERSAO"
    echo "PLATAFORMA=$PLATAFORMA"
    echo "CHECKSUM=$CHECKSUM"
} > "$PKG/pacote.env"

# ── 7. Fechar o tar.gz e assinar por checksum ─────────────────
TAR="$DIST/claude-code-$VERSAO-$PLATAFORMA.tar.gz"
tar -czf "$TAR" -C "$TRABALHO" "claude-code-$VERSAO-$PLATAFORMA"
sha256sum "$TAR" | sed "s|$DIST/||" > "$TAR.sha256"
rm -rf "$PKG" "$GNUPG_TMP"

echo ""
echo "[EMPACOTA] ✅ pacote pronto:"
echo "           $TAR"
echo "           $(du -h "$TAR" | cut -f1)  —  confira com: sha256sum -c $(basename "$TAR").sha256"
echo ""
echo "No servidor: tar -xzf $(basename "$TAR") && cd claude-code-$VERSAO-$PLATAFORMA && bash instalar.sh"
