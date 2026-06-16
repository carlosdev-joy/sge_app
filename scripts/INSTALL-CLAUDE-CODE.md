# Instalação do Claude Code CLI

Scripts para instalar o **Claude Code CLI** com todas as dependências em
**Windows** ou **macOS** (Linux suportado como fallback). Os scripts detectam o
sistema, usam o gerenciador de pacotes adequado, são **idempotentes** (não
reinstalam o que já existe) e validam o resultado ao final.

## O que é instalado / garantido

- **Node.js (LTS)** + **npm** — requisito do Claude Code (Node >= 18)
- **Git**
- **Claude Code CLI** — `@anthropic-ai/claude-code`, global via npm
- Ajuste de **PATH** (e variáveis de ambiente) para que o comando `claude` fique
  disponível no terminal

| SO      | Script                      | Gerenciador de pacotes        |
|---------|-----------------------------|-------------------------------|
| Windows | `install-claude-code.ps1`   | winget → Chocolatey (fallback)|
| macOS   | `install-claude-code.sh`    | Homebrew                      |
| Linux   | `install-claude-code.sh`    | apt / dnf / pacman            |

## Uso

### Windows (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-claude-code.ps1
```

> Dica: execute em um PowerShell **como Administrador** caso o winget/Chocolatey
> precise de privilégios para instalar pacotes a nível de máquina.

### macOS / Linux (bash)

```bash
bash scripts/install-claude-code.sh
```

## Validação

Ao final, os scripts exibem as versões de `node`, `npm`, `git` e `claude` e
executam `claude --version` para confirmar o funcionamento. Para um diagnóstico
completo do ambiente, rode manualmente:

```bash
claude doctor
```

## Primeiro uso

Depois de instalar, autentique-se executando `claude` e seguindo o login no
navegador. Se o comando `claude` não for reconhecido logo após a instalação,
**abra um novo terminal** (ou, no macOS/Linux, rode `source ~/.zshrc` /
`source ~/.bashrc`) para recarregar o PATH.

## Comportamento

- **Detecção automática** do SO e do gerenciador de pacotes.
- **Idempotente**: dependências já presentes (e em versão adequada) são apenas
  reportadas, não reinstaladas.
- **Fallbacks de erro**: se a instalação via npm falhar, é usado o instalador
  nativo oficial (`https://claude.ai/install.sh` / `install.ps1`); no Windows,
  o Chocolatey é instalado sob demanda quando winget não está disponível.
