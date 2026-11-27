<#
.SYNOPSIS
    Ejecuta el worker de impresión térmica 80 mm (PRB-107 / PRB-108).
.DESCRIPTION
    Carga las variables del archivo .env del repositorio (sin exponer secretos),
    habilita logs rotativos UTF-8 en logs/impresion/worker.log y heartbeat JSON
    en logs/impresion/health.json, e inicia `manage.py despachar_impresion`.
#>
[CmdletBinding()]
param(
    [switch]$Once,
    [double]$Intervalo = 2.0,
    [int]$Limite = 20,
    [int]$MaxCiclos = 0,
    [string]$Modo = "",
    [string]$HostImpresora = "",
    [int]$PuertoImpresora = 0,
    [string]$LogDir = "",
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$EnvFile = Join-Path $RepoRoot ".env"

if (Test-Path $EnvFile) {
    Get-Content -Path $EnvFile -Encoding UTF8 | ForEach-Object {
        $linea = $_.Trim()
        if (-not $linea -or $linea.StartsWith("#")) {
            return
        }
        $idx = $linea.IndexOf("=")
        if ($idx -le 0) {
            return
        }
        $clave = $linea.Substring(0, $idx).Trim()
        $valor = $linea.Substring($idx + 1).Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($clave, $valor, "Process")
    }
}

if (-not $PythonExe) {
    $candidatos = @(
        (Join-Path $RepoRoot "venv\Scripts\python.exe"),
        (Join-Path $RepoRoot ".venv\Scripts\python.exe")
    )
    foreach ($c in $candidatos) {
        if (Test-Path $c) {
            $PythonExe = $c
            break
        }
    }
}

if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    throw "No se encontró el intérprete Python del entorno virtual en $RepoRoot (venv/.venv)."
}

if (-not $LogDir) {
    $LogDir = Join-Path $RepoRoot "logs\impresion"
}
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$LogFile = Join-Path $LogDir "worker.log"
$HealthFile = Join-Path $LogDir "health.json"

$ArgsList = @(
    (Join-Path $RepoRoot "manage.py"),
    "despachar_impresion",
    "--limite", "$Limite",
    "--log-file", $LogFile,
    "--health-file", $HealthFile
)

if ($Once) {
    $ArgsList += "--once"
} else {
    $ArgsList += @("--loop", "--intervalo", "$Intervalo")
    if ($MaxCiclos -gt 0) {
        $ArgsList += @("--max-ciclos", "$MaxCiclos")
    }
}

if ($Modo) {
    $ArgsList += @("--modo", $Modo)
}
if ($HostImpresora) {
    $ArgsList += @("--host", $HostImpresora)
}
if ($PuertoImpresora -gt 0) {
    $ArgsList += @("--port", "$PuertoImpresora")
}

Push-Location $RepoRoot
try {
    & $PythonExe @ArgsList
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
