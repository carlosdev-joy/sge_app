<#
.SYNOPSIS
    Instalador do Claude Code CLI para Windows.

.DESCRIPTION
    - Usa winget (ou Chocolatey como fallback) para instalar dependencias.
    - Garante Node.js (LTS) + npm e Git, sem reinstalar o que ja existe.
    - Instala o Claude Code CLI globalmente via npm (@anthropic-ai/claude-code).
    - Garante que o binario esteja no PATH e valida as versoes instaladas.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install-claude-code.ps1
#>

#Requires -Version 5.1
$ErrorActionPreference = 'Continue'   # erros externos nao abortam o script
$NodeMinMajor = 18                    # Claude Code requer Node.js >= 18

# ----- Saida colorida ---------------------------------------------------------
function Info($m)  { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m)    { Write-Host " ok  $m" -ForegroundColor Green }
function Warn($m)  { Write-Host "aviso $m" -ForegroundColor Yellow }
function Err($m)   { Write-Host "erro  $m" -ForegroundColor Red }
function Have($cmd){ [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

# ----- Recarrega PATH do processo (pega instalacoes feitas agora) -------------
function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = (@($machine, $user) | Where-Object { $_ }) -join ';'
    # Limpa o cache de buscas de comandos do PowerShell
    $env:Path = $env:Path   # trigger re-eval
}

# ----- Gerenciador de pacotes -------------------------------------------------
function Get-Pm {
    if (Have winget) { return 'winget' }
    if (Have choco)  { return 'choco'  }
    return $null
}

function Install-Choco {
    if (Have choco) { return }
    Info "Instalando Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    Refresh-Path
}

function Install-Pkg($wingetId, $chocoId) {
    $pm = Get-Pm
    switch ($pm) {
        'winget' {
            winget install --id $wingetId `
                --silent --accept-source-agreements --accept-package-agreements --source winget
            # winget retorna codigos nao-zero para "ja instalado" — tratamos como sucesso
            if ($LASTEXITCODE -ne 0) {
                Warn "winget retornou $LASTEXITCODE (provavel 'ja instalado' — ignorando)."
            }
        }
        'choco' {
            choco install $chocoId -y
        }
        default {
            Warn "winget/choco ausentes; instalando Chocolatey automaticamente..."
            Install-Choco
            choco install $chocoId -y
        }
    }
    Refresh-Path
}

# ----- Node.js + npm ----------------------------------------------------------
function Get-NodeMajor {
    if (-not (Have node)) { return 0 }
    try {
        $v = (& node -v 2>$null) -replace '^v', ''
        return [int]($v.Split('.')[0])
    } catch { return 0 }
}

function Ensure-Node {
    $maj = Get-NodeMajor
    if ($maj -ge $NodeMinMajor) {
        Ok "Node.js $(& node -v 2>$null) ja presente (>= $NodeMinMajor)."
        return
    }
    if ($maj -gt 0) { Warn "Node.js $(& node -v 2>$null) antigo (< $NodeMinMajor); atualizando..." }
    else            { Info "Node.js nao encontrado; instalando LTS..." }

    Install-Pkg 'OpenJS.NodeJS.LTS' 'nodejs-lts'
    Refresh-Path

    if (-not (Have node)) {
        Err "Falha ao instalar Node.js. Instale manualmente em https://nodejs.org e reexecute."
        exit 1
    }
    Ok "Node.js $(& node -v 2>$null) / npm $(& npm -v 2>$null) instalados."
}

# ----- Git --------------------------------------------------------------------
function Ensure-Git {
    if (Have git) {
        $gv = (& git --version 2>$null) -replace 'git version ', ''
        Ok "Git $gv ja presente."
        return
    }
    Info "Git nao encontrado; instalando..."
    Install-Pkg 'Git.Git' 'git'
    Refresh-Path
    if (-not (Have git)) {
        Err "Falha ao instalar Git. Instale manualmente em https://git-scm.com e reexecute."
        exit 1
    }
    Ok "Git instalado."
}

# ----- PATH do npm global (Windows: prefix e o proprio diretorio de binarios) -
function Ensure-NpmPath {
    $prefix = (& npm config get prefix 2>$null | Out-String).Trim()
    if (-not $prefix -or $prefix -eq 'undefined') { return }

    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($userPath -notlike "*$prefix*") {
        $newPath = (@($userPath, $prefix) | Where-Object { $_ }) -join ';'
        [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
        Info "PATH do usuario atualizado: $prefix"
    }
    Refresh-Path
}

# ----- Claude Code CLI --------------------------------------------------------
function Ensure-Claude {
    if (Have claude) {
        $cv = (& claude --version 2>$null | Select-Object -First 1)
        Ok "Claude Code ja instalado ($cv)."
        Info "Atualizando para a versao mais recente..."
    } else {
        Info "Instalando Claude Code CLI via npm..."
    }

    & npm install -g '@anthropic-ai/claude-code'
    $npmOk = ($LASTEXITCODE -eq 0)

    if (-not $npmOk) {
        Warn "npm install falhou (code $LASTEXITCODE); tentando instalador nativo oficial..."
        try {
            Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
        } catch {
            Err "Instalador nativo tambem falhou: $_"
            exit 1
        }
    }

    Ensure-NpmPath

    # Força nova busca no PATH para que "Have claude" reencontre o binario
    $env:Path = $env:Path
}

# ----- Execucao principal -----------------------------------------------------
Info "Sistema: Windows $([Environment]::OSVersion.Version)"
$pm = Get-Pm
if ($pm) { Info "Gerenciador de pacotes: $pm" }
else     { Warn "winget/choco nao detectados; Chocolatey sera instalado sob demanda." }

Ensure-Node
Ensure-Git
Ensure-NpmPath
Ensure-Claude

# ----- Validacao --------------------------------------------------------------
Write-Host ""
Info "Validacao:"
Write-Host "  node   : $(& node -v 2>$null)"
Write-Host "  npm    : $(& npm -v 2>$null)"
Write-Host "  git    : $((& git --version 2>$null) -replace 'git version ','')"
Write-Host "  claude : $(& claude --version 2>$null | Select-Object -First 1)"

Write-Host ""
if (Have claude) {
    Info "Confirmacao (claude --version):"
    & claude --version
    Write-Host ""
    Ok "Claude Code CLI pronto. Para diagnostico completo: claude doctor"
    Ok "Autentique-se com: claude  (login no primeiro uso)"
    Warn "Abra um novo terminal se 'claude' nao for reconhecido nesta sessao."
} else {
    Err "Comando 'claude' nao encontrado no PATH. Revise as mensagens acima."
    exit 1
}
