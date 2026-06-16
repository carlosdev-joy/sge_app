#!/usr/bin/env bash
#
# install-claude-code.sh
# ----------------------------------------------------------------------------
# Instalador do Claude Code CLI para macOS (e Linux como fallback).
#
# - Detecta o sistema operacional e usa o gerenciador de pacotes adequado
#   (Homebrew no macOS; apt/dnf/pacman no Linux).
# - Garante Node.js (LTS) + npm e Git, sem reinstalar o que já existe.
# - Instala o Claude Code CLI globalmente via npm (@anthropic-ai/claude-code).
# - Garante que o binário esteja no PATH e valida as versões instaladas.
#
# Uso:
#   bash scripts/install-claude-code.sh
# ----------------------------------------------------------------------------
set -uo pipefail

# ----- Saída enxuta e legível ------------------------------------------------
if [ -t 1 ]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; RED=""; DIM=""; RESET=""
fi
info()  { printf "%s==>%s %s\n" "$BOLD"   "$RESET" "$*"; }
ok()    { printf "%s ok %s %s\n" "$GREEN"  "$RESET" "$*"; }
warn()  { printf "%saviso%s %s\n" "$YELLOW" "$RESET" "$*"; }
err()   { printf "%serro %s %s\n" "$RED"    "$RESET" "$*" >&2; }
have()  { command -v "$1" >/dev/null 2>&1; }

NODE_MIN_MAJOR=18   # Claude Code requer Node.js >= 18

# ----- Detecção de SO --------------------------------------------------------
OS="$(uname -s)"
case "$OS" in
  Darwin) PLATFORM="macos" ;;
  Linux)  PLATFORM="linux" ;;
  *)      err "Sistema não suportado por este script: $OS (use install-claude-code.ps1 no Windows)."; exit 1 ;;
esac
info "Sistema detectado: ${BOLD}${PLATFORM}${RESET}"

# ----- Detecta gerenciador de pacotes ----------------------------------------
PKG=""
if [ "$PLATFORM" = "macos" ]; then
  PKG="brew"
else
  for c in apt-get dnf pacman; do have "$c" && { PKG="$c"; break; }; done
fi

# sudo apenas quando necessário (Linux sem root)
SUDO=""
if [ "$PLATFORM" = "linux" ] && [ "$(id -u)" -ne 0 ]; then have sudo && SUDO="sudo"; fi

pkg_install() {
  # pkg_install <nome-do-pacote>
  case "$PKG" in
    brew)    brew install "$1" ;;
    apt-get) $SUDO apt-get update -qq && $SUDO apt-get install -y "$1" ;;
    dnf)     $SUDO dnf install -y "$1" ;;
    pacman)  $SUDO pacman -Sy --noconfirm "$1" ;;
    *)       return 1 ;;
  esac
}

ensure_homebrew() {
  [ "$PLATFORM" = "macos" ] || return 0
  if have brew; then ok "Homebrew já instalado."; return 0; fi
  info "Instalando Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" </dev/null || {
    err "Falha ao instalar Homebrew."; return 1; }
  # Carrega o brew no shell atual (Apple Silicon x Intel)
  for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [ -x "$p" ] && eval "$("$p" shellenv)"
  done
  have brew && ok "Homebrew instalado." || return 1
}

# ----- Node.js + npm ---------------------------------------------------------
node_major() { node -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/'; }

ensure_node() {
  if have node; then
    local maj; maj="$(node_major)"
    if [ -n "$maj" ] && [ "$maj" -ge "$NODE_MIN_MAJOR" ]; then
      ok "Node.js $(node -v) já presente (>= ${NODE_MIN_MAJOR})."
      return 0
    fi
    warn "Node.js $(node -v) é antigo (< ${NODE_MIN_MAJOR}); atualizando..."
  else
    info "Node.js não encontrado; instalando versão LTS..."
  fi

  if [ "$PLATFORM" = "macos" ]; then
    pkg_install node || { err "Falha ao instalar Node.js via Homebrew."; return 1; }
  else
    # Linux: tenta repositório oficial NodeSource (LTS) e cai no gerenciador do SO
    if [ -n "$PKG" ] && ! pkg_install nodejs; then
      warn "Pacote 'nodejs' do sistema falhou; tentando NodeSource (LTS)..."
      curl -fsSL https://deb.nodesource.com/setup_lts.x | $SUDO -E bash - 2>/dev/null \
        && pkg_install nodejs || { err "Falha ao instalar Node.js."; return 1; }
    fi
  fi
  have node && have npm && ok "Node.js $(node -v) / npm $(npm -v) instalados."
}

# ----- Git -------------------------------------------------------------------
ensure_git() {
  if have git; then ok "Git $(git --version | awk '{print $3}') já presente."; return 0; fi
  info "Git não encontrado; instalando..."
  pkg_install git || { err "Falha ao instalar Git."; return 1; }
  have git && ok "Git instalado."
}

# ----- PATH do npm global (evita EACCES sem sudo) ----------------------------
ensure_npm_path() {
  local prefix bindir
  prefix="$(npm config get prefix 2>/dev/null)"
  # Se o prefixo global não for gravável, redireciona para ~/.npm-global
  if [ ! -w "$prefix" ] && [ "$PLATFORM" = "linux" ]; then
    prefix="$HOME/.npm-global"
    npm config set prefix "$prefix" >/dev/null 2>&1
    warn "Diretório global sem permissão; usando prefixo ${prefix}."
  fi
  bindir="$prefix/bin"
  case ":$PATH:" in
    *":$bindir:"*) : ;;
    *)
      export PATH="$bindir:$PATH"
      for rc in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.profile"; do
        [ -f "$rc" ] || continue
        grep -qsF "$bindir" "$rc" || {
          printf '\n# Claude Code CLI (npm global bin)\nexport PATH="%s:$PATH"\n' "$bindir" >> "$rc"
          info "PATH atualizado em ${DIM}${rc}${RESET}"
        }
      done
      ;;
  esac
}

# ----- Claude Code CLI -------------------------------------------------------
ensure_claude() {
  if have claude; then
    ok "Claude Code já instalado ($(claude --version 2>/dev/null | head -n1))."
    info "Atualizando para a versão mais recente..."
  else
    info "Instalando Claude Code CLI via npm..."
  fi
  if ! npm install -g @anthropic-ai/claude-code; then
    warn "Instalação via npm falhou; tentando o instalador nativo oficial..."
    curl -fsSL https://claude.ai/install.sh | bash || { err "Falha ao instalar o Claude Code CLI."; return 1; }
  fi
  ensure_npm_path
  hash -r 2>/dev/null || true
}

# ----- Execução --------------------------------------------------------------
[ "$PLATFORM" = "macos" ] && { ensure_homebrew || exit 1; }
[ -z "$PKG" ] && warn "Nenhum gerenciador de pacotes detectado; etapas de instalação podem falhar."

ensure_node || exit 1
ensure_git  || exit 1
ensure_npm_path
ensure_claude || exit 1

# ----- Validação -------------------------------------------------------------
echo
info "Validação:"
printf "  node   : %s\n" "$(node -v 2>/dev/null || echo 'ausente')"
printf "  npm    : %s\n" "$(npm -v 2>/dev/null || echo 'ausente')"
printf "  git    : %s\n" "$(git --version 2>/dev/null | awk '{print $3}' || echo 'ausente')"
printf "  claude : %s\n" "$(claude --version 2>/dev/null || echo 'ausente')"

echo
if have claude; then
  info "Comando de confirmação (claude --version):"
  claude --version
  echo
  ok "Claude Code CLI pronto. Diagnóstico completo: ${BOLD}claude doctor${RESET}."
  ok "Autentique-se com: ${BOLD}claude${RESET} (login no primeiro uso)."
  warn "Reinicie o terminal (ou rode: source ~/.zshrc) se 'claude' não for encontrado."
else
  err "O comando 'claude' não ficou disponível no PATH. Revise as mensagens acima."
  exit 1
fi
