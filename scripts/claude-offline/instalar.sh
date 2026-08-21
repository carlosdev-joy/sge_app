#!/bin/bash
# =============================================================
# instalar.sh — instala o Claude Code no servidor SEM internet.
#
# Roda DENTRO da pasta do pacote, com o binário ao lado. Não
# baixa nada: tudo que precisa veio no .tar.gz.
#
# Uso: bash instalar.sh
#
# Instala no HOME de quem executa:
#   binário  → ~/.local/share/claude/versions/<versão>
#   atalho   → ~/.local/bin/claude
# Nada vai para /usr nem exige root.
# =============================================================
set -e

AQUI="$(cd "$(dirname "$0")" && pwd)"
cd "$AQUI"

[ -f pacote.env ] || { echo "[INSTALA] ERRO: pacote.env não encontrado — rode dentro da pasta do pacote." >&2; exit 1; }
# shellcheck disable=SC1091
. ./pacote.env

echo "[INSTALA] Claude Code $VERSAO ($PLATAFORMA)"

# ── 1. Recusar sudo ───────────────────────────────────────────
# Com sudo a instalação cairia no HOME do root e o comando 'claude'
# não funcionaria no shell do próprio usuário.
if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    echo "[INSTALA] ERRO: não rode com sudo. Rode como o usuário que vai usar o Claude Code." >&2
    exit 1
fi

# ── 2. O pacote combina com esta máquina? ─────────────────────
case "$(uname -s)" in
    Linux) : ;;
    *) echo "[INSTALA] ERRO: este pacote é de Linux; aqui é $(uname -s)." >&2; exit 1 ;;
esac

case "$(uname -m)" in
    x86_64|amd64)  ARCH_REAL="x64" ;;
    arm64|aarch64) ARCH_REAL="arm64" ;;
    *) echo "[INSTALA] ERRO: arquitetura não suportada: $(uname -m)." >&2; exit 1 ;;
esac

# musl (Alpine) e glibc usam binários diferentes — trocar um pelo
# outro dá "not found" na execução, erro que não nomeia a causa.
if [ -f /lib/libc.musl-x86_64.so.1 ] || [ -f /lib/libc.musl-aarch64.so.1 ] \
   || ldd /bin/ls 2>&1 | grep -q musl; then
    LIBC_REAL="-musl"
else
    LIBC_REAL=""
fi
PLAT_REAL="linux-${ARCH_REAL}${LIBC_REAL}"

if [ "$PLAT_REAL" != "$PLATAFORMA" ]; then
    echo "[INSTALA] ERRO: o pacote é '$PLATAFORMA' e esta máquina é '$PLAT_REAL'." >&2
    echo "          Gere o pacote de novo com a plataforma correta." >&2
    exit 1
fi

# glibc mínima do binário: 2.17 (RHEL 7+, Ubuntu 20.04+, Debian 10+).
if [ -z "$LIBC_REAL" ] && command -v ldd >/dev/null 2>&1; then
    GLIBC=$(ldd --version 2>/dev/null | head -1 | awk '{print $NF}')
    MENOR=$(printf '%s\n2.17\n' "$GLIBC" | sort -V | head -1)
    if [ "$MENOR" != "2.17" ] && [ "$GLIBC" != "2.17" ]; then
        echo "[INSTALA] ERRO: glibc $GLIBC — o binário exige 2.17 ou mais nova." >&2
        exit 1
    fi
    echo "[INSTALA] ✓ glibc $GLIBC"
fi

# ── 3. Conferir o binário (o transporte pode corromper) ───────
[ -f claude ] || { echo "[INSTALA] ERRO: binário 'claude' não está no pacote." >&2; exit 1; }
REAL=$(sha256sum claude | cut -d' ' -f1)
if [ "$REAL" != "$CHECKSUM" ]; then
    echo "[INSTALA] ERRO: SHA256 não confere — o arquivo chegou corrompido." >&2
    echo "          esperado: $CHECKSUM" >&2
    echo "          recebido: $REAL" >&2
    exit 1
fi
echo "[INSTALA] ✓ SHA256 confere"
chmod +x claude

# Assinatura GPG do manifesto, quando há gpg na máquina. Não é
# obrigatória aqui (já foi conferida ao montar o pacote), então
# falha vira aviso, não erro.
if command -v gpg >/dev/null 2>&1 && [ -f manifest.json.sig ]; then
    GNUPG_TMP=$(mktemp -d); chmod 700 "$GNUPG_TMP"
    if gpg --homedir "$GNUPG_TMP" --batch --quiet --import claude-code.asc 2>/dev/null \
       && gpg --homedir "$GNUPG_TMP" --batch --verify manifest.json.sig manifest.json 2>/dev/null; then
        echo "[INSTALA] ✓ assinatura do manifesto válida"
    else
        echo "[INSTALA] ⚠ não foi possível verificar a assinatura do manifesto aqui (siga pelo SHA256 acima)"
    fi
    rm -rf "$GNUPG_TMP"
fi

# ── 4. Instalar ───────────────────────────────────────────────
# Cópia manual, deliberadamente — e NÃO `./claude install`.
# O instalador embutido do binário resolve o canal 'latest' e BAIXA
# da internet: num teste aqui, um pacote 2.1.228 instalou 2.1.238
# vindo da rede. Num servidor sem saída isso falha; numa máquina com
# saída, instala uma versão diferente da que foi homologada. A cópia
# abaixo reproduz exatamente o layout que o instalador nativo cria,
# usando só o que veio no pacote.
echo "[INSTALA] instalando $VERSAO em ~/.local ..."
mkdir -p "$HOME/.local/share/claude/versions" "$HOME/.local/bin"
cp claude "$HOME/.local/share/claude/versions/$VERSAO"
chmod +x "$HOME/.local/share/claude/versions/$VERSAO"
ln -sfn "$HOME/.local/share/claude/versions/$VERSAO" "$HOME/.local/bin/claude"
echo "[INSTALA] ✓ instalado"

case ":$PATH:" in
    *":$HOME/.local/bin:"*) : ;;
    *) echo "[INSTALA] ⚠ ~/.local/bin não está no PATH. Acrescente ao ~/.bashrc:"
       echo '           export PATH="$HOME/.local/bin:$PATH"' ;;
esac

# ── 5. Desligar o auto-update ─────────────────────────────────
# Num servidor de rede controlada a versão é homologada: o binário
# não pode se trocar sozinho. settings.json existente NUNCA é
# sobrescrito — mostramos o que acrescentar e seguimos.
CONF="$HOME/.claude/settings.json"
mkdir -p "$HOME/.claude"

# O bloco "env" leva também o proxy e a CA, quando já estão neste
# shell. Não é firula: variável exportada só no shell não alcança os
# agentes de segundo plano (o supervisor é um processo à parte, que
# herda o ambiente de quem o iniciou primeiro — ou nenhum). Em
# settings.json a configuração vale para toda sessão.
ENV_JSON='    "DISABLE_AUTOUPDATER": "1"'
PROXY_ENV="${HTTPS_PROXY:-${https_proxy:-}}"
if [ -n "$PROXY_ENV" ]; then
    ENV_JSON="$ENV_JSON,
    \"HTTPS_PROXY\": \"$PROXY_ENV\""
fi
if [ -n "${NO_PROXY:-${no_proxy:-}}" ]; then
    ENV_JSON="$ENV_JSON,
    \"NO_PROXY\": \"${NO_PROXY:-$no_proxy}\""
fi
if [ -n "${NODE_EXTRA_CA_CERTS:-}" ]; then
    ENV_JSON="$ENV_JSON,
    \"NODE_EXTRA_CA_CERTS\": \"$NODE_EXTRA_CA_CERTS\""
fi

if [ ! -f "$CONF" ]; then
    printf '{\n  "env": {\n%s\n  }\n}\n' "$ENV_JSON" > "$CONF"
    echo "[INSTALA] ✓ configuração gravada em $CONF"
    # if/fi e não '[ ... ] && echo': sob set -e, o teste falso derruba
    # o script inteiro no último comando do bloco.
    if [ -n "$PROXY_ENV" ]; then
        echo "[INSTALA]   proxy herdado deste shell: $PROXY_ENV"
    fi
else
    # settings.json existente nunca é sobrescrito — mesma regra do
    # deploy.sh para config/ e dags/.
    echo "[INSTALA] ⚠ $CONF já existe — não foi tocado. Acrescente dentro de \"env\":"
    echo "$ENV_JSON"
fi

# ── 6. Diagnóstico ────────────────────────────────────────────
echo ""
echo "[INSTALA] ── diagnóstico ──────────────────────────────"
"$HOME/.local/bin/claude" --version || true

# O Claude Code precisa alcançar api.anthropic.com A CADA mensagem.
# Instalar não resolve isso — por isso o teste vem junto. Qualquer
# resposta HTTP (inclusive 401, que é a esperada sem credencial)
# significa que o caminho de rede existe.
if command -v curl >/dev/null 2>&1; then
    # Sem `|| echo`: na falha o próprio -w já imprime 000, e o echo
    # extra concatenava "000000" — que não casava com o teste e o
    # diagnóstico anunciava sucesso com a rede bloqueada.
    COD=$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' \
          https://api.anthropic.com/v1/messages 2>/dev/null) || true
    if [[ ! "$COD" =~ ^[1-5][0-9][0-9]$ ]]; then
        echo "[INSTALA] ✗ api.anthropic.com inalcançável desta máquina."
        echo "          Sem isso o Claude Code instala mas não responde."
        echo "          Configure o proxy corporativo antes de usar:"
        echo '            export HTTPS_PROXY=http://proxy.empresa:8080'
        echo '            export NODE_EXTRA_CA_CERTS=/caminho/ca-corporativa.pem'
        echo "          e libere no proxy: api.anthropic.com, platform.claude.com, claude.ai"
    else
        echo "[INSTALA] ✓ api.anthropic.com respondeu HTTP $COD — o caminho de rede existe"
        echo "          (qualquer código serve aqui: a sonda vai sem credencial e sem corpo)"
    fi
fi

echo ""
echo "[INSTALA] ✅ pronto. Autentique com uma das opções:"
echo "          • token de assinatura gerado noutra máquina com navegador:"
echo "              claude setup-token   (lá)  →  cole o token aqui"
echo "          • chave da Console:  export ANTHROPIC_API_KEY=sk-ant-..."
echo "          Depois rode:  claude"
