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

# ── 1. Sudo não; root puro sim, avisando ──────────────────────
# Com sudo a instalação cairia no HOME do root e o comando 'claude'
# não funcionaria no shell do próprio usuário — isso é erro.
if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    echo "[INSTALA] ERRO: não rode com sudo. Rode como o usuário que vai usar o Claude Code." >&2
    exit 1
fi
# Root puro (su -, login de root, container) é legítimo e continua —
# mesma decisão do instalador oficial. Mas nomeia onde vai instalar,
# senão o operador procura o comando no login errado.
if [ "$(id -u)" -eq 0 ]; then
    echo "[INSTALA] ⚠ rodando como root: instala em $HOME/.local, só para o root."
    echo "          Para instalar para outro usuário, rode no login dele."
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
    # Só compara quando o que saiu do ldd É um número de versão. Sem
    # esta guarda, um ldd que imprime outra coisa deixa GLIBC vazio, o
    # sort -V devolve a linha vazia e a máquina capaz é barrada por um
    # "ERRO: glibc  — exige 2.17" que não nomeia versão nenhuma.
    case "$GLIBC" in
        [0-9]*.[0-9]*)
            MENOR=$(printf '%s\n2.17\n' "$GLIBC" | sort -V | head -1)
            if [ "$MENOR" != "2.17" ] && [ "$GLIBC" != "2.17" ]; then
                echo "[INSTALA] ERRO: glibc $GLIBC — o binário exige 2.17 ou mais nova." >&2
                exit 1
            fi
            ;;
        *)
            echo "[INSTALA] ⚠ não deu para ler a versão da glibc — seguindo sem essa checagem"
            GLIBC="desconhecida"
            ;;
    esac
    echo "[INSTALA] ✓ glibc $GLIBC"
fi

# ── 3. Conferir o binário (o transporte pode corromper) ───────
# ATENÇÃO ao alcance desta seção: binário, manifesto, assinatura e este
# próprio script viajam no MESMO pacote. Quem consegue alterar o pacote
# altera os quatro de uma vez, e as conferências abaixo continuariam
# passando. Elas provam INTEGRIDADE DE TRANSPORTE (arquivo truncado,
# byte trocado no scp), não autenticidade. A autenticidade é conferida
# na montagem, na máquina com internet: lá o manifesto é validado contra
# a chave de release da Anthropic. Quem quiser a garantia ponta a ponta
# compara o .sha256 publicado na release com o gerado no empacotamento.
[ -f claude ] || { echo "[INSTALA] ERRO: binário 'claude' não está no pacote." >&2; exit 1; }
REAL=$(sha256sum claude | cut -d' ' -f1)
if [ "$REAL" != "$CHECKSUM" ]; then
    echo "[INSTALA] ERRO: SHA256 não confere — o arquivo chegou corrompido." >&2
    echo "          esperado: $CHECKSUM" >&2
    echo "          recebido: $REAL" >&2
    exit 1
fi
echo "[INSTALA] ✓ SHA256 do binário confere (integridade do transporte)"
chmod +x claude

# O fingerprint é pinado aqui também. Não fecha o buraco descrito acima
# — o pin viaja no mesmo pacote —, mas eleva a barra: já não basta
# reassinar o manifesto com outra chave, é preciso editar este script.
FINGERPRINT="31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE"
if command -v gpg >/dev/null 2>&1 && [ -f manifest.json.sig ]; then
    GNUPG_TMP=$(mktemp -d); chmod 700 "$GNUPG_TMP"
    STATUS=""
    if gpg --homedir "$GNUPG_TMP" --batch --quiet --import claude-code.asc 2>/dev/null; then
        STATUS=$(gpg --homedir "$GNUPG_TMP" --batch --status-fd 1 --verify \
                 manifest.json.sig manifest.json 2>/dev/null || true)
    fi
    if printf '%s\n' "$STATUS" | grep '^\[GNUPG:\] VALIDSIG ' | grep -q "$FINGERPRINT"; then
        echo "[INSTALA] ✓ manifesto do pacote assinado pela chave de release"
    else
        echo "[INSTALA] ⚠ assinatura do manifesto não confere com $FINGERPRINT"
        echo "          O pacote pode ter sido montado fora do procedimento — confira a origem."
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
# Escapa " e \ — uma senha de proxy com qualquer um dos dois geraria um
# JSON inválido, e settings.json que não parseia derruba a configuração
# inteira, inclusive o DISABLE_AUTOUPDATER.
_json() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

ENV_JSON='    "DISABLE_AUTOUPDATER": "1"'
PROXY_ENV="${HTTPS_PROXY:-${https_proxy:-}}"
if [ -n "$PROXY_ENV" ]; then
    ENV_JSON="$ENV_JSON,
    \"HTTPS_PROXY\": \"$(_json "$PROXY_ENV")\""
fi
if [ -n "${NO_PROXY:-${no_proxy:-}}" ]; then
    ENV_JSON="$ENV_JSON,
    \"NO_PROXY\": \"$(_json "${NO_PROXY:-$no_proxy}")\""
fi
if [ -n "${NODE_EXTRA_CA_CERTS:-}" ]; then
    ENV_JSON="$ENV_JSON,
    \"NODE_EXTRA_CA_CERTS\": \"$(_json "$NODE_EXTRA_CA_CERTS")\""
fi

if [ ! -f "$CONF" ]; then
    # umask antes de criar: o arquivo pode conter a senha do proxy
    # (HTTPS_PROXY com usuario:senha@), e o padrão 0644 a deixaria
    # legível por qualquer conta do servidor.
    ( umask 077 && printf '{\n  "env": {\n%s\n  }\n}\n' "$ENV_JSON" > "$CONF" )
    chmod 600 "$CONF"
    echo "[INSTALA] ✓ configuração gravada em $CONF (modo 600)"
    # if/fi e não '[ ... ] && echo': sob set -e, o teste falso derruba
    # o script inteiro no último comando do bloco.
    if [ -n "$PROXY_ENV" ]; then
        echo "[INSTALA]   proxy herdado deste shell: $PROXY_ENV"
        case "$PROXY_ENV" in
            *://*@*)
                echo "[INSTALA] ⚠ a URL do proxy carrega usuário:senha, agora gravada em $CONF."
                echo "          O arquivo está 600, mas root e backup o leem. Se der, prefira"
                echo "          um proxy sem autenticação por URL para esta conta." ;;
        esac
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

# O Claude Code precisa alcançar api.anthropic.com A CADA mensagem, e
# instalar não resolve isso — por isso a sonda vem junto.
#
# Não basta "veio um código HTTP": num proxy corporativo, 407 (exige
# autenticação) e a página de bloqueio (403, ou 200 com HTML) também são
# respostas HTTP, e o Claude Code não funciona em nenhum dos casos. A
# sonda pede GET /v1/models sem credencial: a API responde 401 com
# `authentication_error` no corpo. Só isso prova que quem respondeu foi
# a API, e não algo no meio do caminho.
if command -v curl >/dev/null 2>&1; then
    # Sem `|| echo`: na falha o próprio -w já imprime 000, e o echo
    # extra concatenava "000000" — que não casava com o teste e o
    # diagnóstico anunciava sucesso com a rede bloqueada.
    # O stderr do curl é guardado porque em HTTPS o proxy recusa no
    # CONNECT: o 407 não vira %{http_code} (que fica 000), só aparece na
    # mensagem "Received HTTP code 407 from proxy after CONNECT". Sem
    # ler o stderr, o diagnóstico culpa a rede quando o problema é
    # credencial de proxy — testado com um proxy que devolve 407.
    ERRO_CURL=$(mktemp)
    RESP=$(curl -sS --max-time 10 -w '\n%{http_code}' \
           https://api.anthropic.com/v1/models 2>"$ERRO_CURL") || true
    MSG_CURL=$(cat "$ERRO_CURL"); rm -f "$ERRO_CURL"
    COD=$(printf '%s' "$RESP" | tail -1)
    CORPO=$(printf '%s' "$RESP" | sed '$d')

    if [ "$COD" = "401" ] && printf '%s' "$CORPO" | grep -q "authentication_error"; then
        echo "[INSTALA] ✓ api.anthropic.com respondeu como a API (401 sem credencial) — caminho ok"
    elif [ "$COD" = "407" ] || printf '%s' "$MSG_CURL" | grep -q "407"; then
        echo "[INSTALA] ✗ o proxy exige autenticação (HTTP 407)."
        echo "          Ponha as credenciais na URL, ex.:"
        echo '            export HTTPS_PROXY=http://usuario:senha@proxy.empresa:8080'
        echo "          ou peça ao time de rede uma exceção sem autenticação para este servidor."
    elif [[ "$COD" =~ ^[1-5][0-9][0-9]$ ]]; then
        echo "[INSTALA] ✗ algo respondeu HTTP $COD, mas não é a API da Anthropic."
        echo "          Sinal clássico de portal de bloqueio ou inspeção do proxy no meio."
        echo "          Peça a liberação de api.anthropic.com e confira NODE_EXTRA_CA_CERTS."
    else
        echo "[INSTALA] ✗ api.anthropic.com inalcançável desta máquina."
        if [ -n "$MSG_CURL" ]; then
            echo "          curl: $(printf '%s' "$MSG_CURL" | head -1)"
        fi
        echo "          Sem isso o Claude Code instala mas não responde."
        echo "          Configure o proxy corporativo antes de usar:"
        echo '            export HTTPS_PROXY=http://proxy.empresa:8080'
        echo '            export NODE_EXTRA_CA_CERTS=/caminho/ca-corporativa.pem'
        echo "          e libere no proxy: api.anthropic.com, platform.claude.com, claude.ai"
    fi
fi

echo ""
echo "[INSTALA] ✅ pronto. Autentique com uma das opções:"
echo "          • token de assinatura gerado noutra máquina com navegador:"
echo "              claude setup-token   (lá)  →  cole o token aqui"
echo "          • chave da Console:  export ANTHROPIC_API_KEY=sk-ant-..."
echo "          Depois rode:  claude"
