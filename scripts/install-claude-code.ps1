<#
.SYNOPSIS
    Instalador do Claude Code CLI para Windows.

.DESCRIPTION
    - Usa winget (ou Chocolatey como fallback) para instalar dependências.
    - Garante Node.js (LTS) + npm e Git, sem reinstalar o que já existe.
    - Instala o Claude Code CLI globalmente via npm (@anthropic-ai/claude-code).
    - Garante que o binário esteja no PATH e valida as versões instaladas.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install-claude-code.ps1
#>

#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$NodeMinMajor = 18   # Claude Code requer Node.js >= 18

# ----- Saída enxuta ----------------------------------------------------------
function Info($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host " ok  $m" -ForegroundColor Green }
function Warn($m) { Write-Host "aviso $m" -ForegroundColor Yellow }
function Err($m)  { Write-Host "erro  $m" -ForegroundColor Red }
function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

function Refresh-Path {
    # Recarrega o PATH do processo a partir das variáveis de Máquina + Usuário
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = (@($machine, $user) | Where-Object { $_ }) -join ';'
}

# ----- Detecção do gerenciador de pacotes ------------------------------------
function Get-PackageManager {
    if (Have winget) { return 'winget' }
    if (Have choco)  { return 'choco'  }
    return $null
}

function Install-Choco {
    if (Have choco) { return }
    Info "Instalando Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    Refresh-Path
}

function Install-Package($wingetId, $chocoId) {
    $pm = Get-PackageManager
    switch ($pm) {
        'winget' {
            winget install --id $wingetId --silent --accept-source-agreements --accept-package-agreements --source winget
        }
        'choco'  { choco install $chocoId -y }
        default  {
            Warn "Nenhum gerenciador de pacotes (winget/choco) encontrado; instalando Chocolatey..."
            Install-Choco
            choco install $chocoId -y
        }
    }
    Refresh-Path
}

# ----- Node.js + npm ---------------------------------------------------------
function Get-NodeMajor {
    if (-not (Have node)) { return 0 }
    $v = (node -v) -replace '^v',''
    return [int]($v.Split('.')[0])
}

function Ensure-Node {
    $maj = Get-NodeMajor
    if ($maj -ge $NodeMinMajor) {
        Ok "Node.js $(node -v) já presente (>= $NodeMinMajor)."
        return
    }
    if ($maj -gt 0) { Warn "Node.js $(node -v) é antigo (< $NodeMinMajor); atualizando..." }
    else            { Info "Node.js não encontrado; instalando versão LTS..." }
    Install-Package 'OpenJS.NodeJS.LTS' 'nodejs-lts'
    if (-not (Have node)) { throw "Falha ao instalar Node.js." }
    Ok "Node.js $(node -v) / npm $(npm -v) instalados."
}

# ----- Git -------------------------------------------------------------------
function Ensure-Git {
    if (Have git) { Ok "Git $((git --version).Split(' ')[2]) já presente."; return }
    Info "Git não encontrado; instalando..."
    Install-Package 'Git.Git' 'git'
    if (-not (Have git)) { throw "Falha ao instalar Git." }
    Ok "Git instalado."
}

# ----- PATH do npm global ----------------------------------------------------
function Ensure-NpmPath {
    $prefix = (npm config get prefix) 2>$null
    if (-not $prefix) { return }
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($userPath -notlike "*$prefix*") {
        $newPath = (@($userPath, $prefix) | Where-Object { $_ }) -join ';'
        [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
        Info "PATH do usuário atualizado com $prefix"
    }
    Refresh-Path
}

# ----- Claude Code CLI -------------------------------------------------------
function Ensure-Claude {
    if (Have claude) {
        Ok "Claude Code já instalado ($((claude --version) 2>$null))."
        Info "Atualizando para a versão mais recente..."
    } else {
        Info "Instalando Claude Code CLI via npm..."
    }
    try {
        npm install -g '@anthropic-ai/claude-code'
    } catch {
        Warn "Instalação via npm falhou; tentando o instalador nativo oficial..."
        Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
    }
    Ensure-NpmPath
}

# ----- Execução --------------------------------------------------------------
Info "Sistema detectado: Windows ($([Environment]::OSVersion.Version))"
$pm = Get-PackageManager
if ($pm) { Info "Gerenciador de pacotes: $pm" } else { Warn "winget/choco ausentes; Chocolatey será instalado sob demanda." }

Ensure-Node
Ensure-Git
Ensure-NpmPath
Ensure-Claude

# ----- Validação -------------------------------------------------------------
Write-Host ""
Info "Validação:"
"  node   : $((node -v)   2>$null)"
"  npm    : $((npm -v)    2>$null)"
"  git    : $(((git --version) 2>$null) -replace 'git version ','')"
"  claude : $((claude --version) 2>$null)"

Write-Host ""
if (Have claude) {
    Info "Comando de confirmação (claude --version):"
    claude --version
    Write-Host ""
    Ok "Claude Code CLI pronto. Diagnóstico completo: claude doctor."
    Ok "Autentique-se com: claude (login no primeiro uso)."
    Warn "Abra um novo terminal se o comando 'claude' não for reconhecido nesta sessão."
} else {
    Err "O comando 'claude' não ficou disponível no PATH. Revise as mensagens acima."
    exit 1
}
