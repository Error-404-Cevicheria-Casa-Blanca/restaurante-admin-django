<#
.SYNOPSIS
Ejecuta la suite de pruebas de Django (manage.py test) con entorno reproducible.
#>
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$TestArgs
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot

$PrevSecretKey = $env:DJANGO_SECRET_KEY
$PrevDbVars = @{
    DB_NAME     = $env:DB_NAME
    DB_USER     = $env:DB_USER
    DB_PASSWORD = $env:DB_PASSWORD
    DB_HOST     = $env:DB_HOST
    DB_PORT     = $env:DB_PORT
}

try {
    $CandidatosPython = @(
        (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
        (Join-Path $RepoRoot "venv\Scripts\python.exe"),
        "python"
    )

    $PythonExe = $null
    foreach ($cand in $CandidatosPython) {
        if ($cand -eq "python" -or (Test-Path $cand)) {
            try {
                & $cand -c "import django" 2>$null
                if ($LASTEXITCODE -eq 0) {
                    $PythonExe = $cand
                    break
                }
            } catch {
                continue
            }
        }
    }

    if (-not $PythonExe) {
        Write-Error "No se encontró un intérprete Python con Django instalado (.venv, venv o PATH)."
        exit 1
    }

    if (-not $env:DJANGO_SECRET_KEY) {
        $env:DJANGO_SECRET_KEY = "clave-solo-pruebas-locales-NO-USAR-en-produccion"
    }
    $env:PYTHONUNBUFFERED = "1"

    # Si hay variables DB_* parciales en el entorno (ej. solo DB_PASSWORD),
    # limpiarlas durante el test para usar el SQLite efímero de Django TestCase.
    $DbDefinidas = @($PrevDbVars.Keys | Where-Object { -not [string]::IsNullOrEmpty($PrevDbVars[$_]) })
    if ($DbDefinidas.Count -gt 0 -and $DbDefinidas.Count -lt 5) {
        foreach ($varName in $PrevDbVars.Keys) {
            Remove-Item "Env:$varName" -ErrorAction SilentlyContinue
        }
    }

    & $PythonExe manage.py test @TestArgs
    exit $LASTEXITCODE
} finally {
    if ($null -eq $PrevSecretKey) {
        Remove-Item "Env:DJANGO_SECRET_KEY" -ErrorAction SilentlyContinue
    } else {
        $env:DJANGO_SECRET_KEY = $PrevSecretKey
    }
    foreach ($varName in $PrevDbVars.Keys) {
        if ($null -eq $PrevDbVars[$varName]) {
            Remove-Item "Env:$varName" -ErrorAction SilentlyContinue
        } else {
            Set-Item "Env:$varName" -Value $PrevDbVars[$varName]
        }
    }
    Pop-Location
}
