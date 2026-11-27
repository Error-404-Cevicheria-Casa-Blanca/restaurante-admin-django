<#
.SYNOPSIS
    Healthcheck del worker de impresión térmica 80 mm (PRB-108).
.DESCRIPTION
    Verifica que el heartbeat JSON (logs/impresion/health.json) esté sano y reciente
    usando `manage.py despachar_impresion --healthcheck`. Opcionalmente reinicia el
    servicio o tarea programada si detecta fallo (-RestartOnFailure).
#>
[CmdletBinding()]
param(
    [string]$NombreServicio = "CasaBlancaImpresionWorker",
    [string]$HealthFile = "",
    [int]$MaxAgeSeconds = 30,
    [string]$PythonExe = "",
    [switch]$RestartOnFailure
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $HealthFile) {
    $HealthFile = Join-Path $RepoRoot "logs\impresion\health.json"
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
    throw "No se encontró el intérprete Python del entorno virtual en $RepoRoot."
}

$EnvFile = Join-Path $RepoRoot ".env"
if (Test-Path $EnvFile) {
    Get-Content -Path $EnvFile -Encoding UTF8 | ForEach-Object {
        $linea = $_.Trim()
        if (-not $linea -or $linea.StartsWith("#")) { return }
        $idx = $linea.IndexOf("=")
        if ($idx -le 0) { return }
        $clave = $linea.Substring(0, $idx).Trim()
        $valor = $linea.Substring($idx + 1).Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($clave, $valor, "Process")
    }
}

Push-Location $RepoRoot
try {
    & $PythonExe (Join-Path $RepoRoot "manage.py") despachar_impresion `
        --healthcheck `
        --health-file $HealthFile `
        --max-age-seconds $MaxAgeSeconds
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($exitCode -eq 0) {
    exit 0
}

if ($RestartOnFailure) {
    Write-Warning "[PRB-108] Heartbeat fallido (exit=$exitCode). Intentando reiniciar '$NombreServicio'..."
    $svc = Get-Service -Name $NombreServicio -ErrorAction SilentlyContinue
    if ($svc) {
        Restart-Service -Name $NombreServicio -Force
        Write-Output "[PRB-108] Servicio Windows '$NombreServicio' reiniciado."
    } else {
        $task = Get-ScheduledTask -TaskName $NombreServicio -ErrorAction SilentlyContinue
        if ($task) {
            Stop-ScheduledTask -TaskName $NombreServicio -ErrorAction SilentlyContinue
            Start-ScheduledTask -TaskName $NombreServicio
            Write-Output "[PRB-108] Tarea Programada '$NombreServicio' reiniciada."
        } else {
            Write-Warning "[PRB-108] No se encontró servicio ni tarea programada '$NombreServicio'."
        }
    }
}

exit $exitCode
