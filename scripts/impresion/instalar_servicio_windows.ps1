<#
.SYNOPSIS
    Instala o desinstala el servicio Windows / tarea programada del worker de impresión (PRB-108).
.DESCRIPTION
    Soporta dos modos de instalación con recuperación automática tras reinicio:
    - NSSM: instala un Servicio Windows real con rotación de logs y reinicio automático.
    - TaskScheduler: registra una Tarea Programada nativa al inicio del sistema con reinicio
      automático (no requiere herramientas de terceros).
#>
[CmdletBinding()]
param(
    [ValidateSet("Auto", "NSSM", "TaskScheduler")]
    [string]$ModoInstalacion = "Auto",
    [string]$NombreServicio = "CasaBlancaImpresionWorker",
    [double]$Intervalo = 2.0,
    [int]$Limite = 20,
    [string]$NssmPath = "",
    [switch]$Uninstall,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RunnerScript = Join-Path $PSScriptRoot "run_worker_impresion.ps1"
$HealthScript = Join-Path $PSScriptRoot "healthcheck_worker_impresion.ps1"
$LogDir = Join-Path $RepoRoot "logs\impresion"
$TaskMonitorName = "${NombreServicio}_Healthcheck"

if (-not (Test-Path $RunnerScript)) {
    throw "No se encontró el runner: $RunnerScript"
}

function Resolve-NssmBinary {
    param([string]$ExplicitPath)
    if ($ExplicitPath -and (Test-Path $ExplicitPath)) {
        return (Resolve-Path $ExplicitPath).Path
    }
    $cmd = Get-Command "nssm.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    return $null
}

$NssmExe = Resolve-NssmBinary -ExplicitPath $NssmPath
$ModoEfectivo = $ModoInstalacion
if ($ModoEfectivo -eq "Auto") {
    $ModoEfectivo = if ($NssmExe) { "NSSM" } else { "TaskScheduler" }
}
if ($ModoEfectivo -eq "NSSM" -and -not $NssmExe) {
    throw "Se solicitó ModoInstalacion=NSSM pero nssm.exe no está en PATH ni en -NssmPath."
}

$PsExe = (Get-Command "powershell.exe").Source
$RunnerArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$RunnerScript`" -Intervalo $Intervalo -Limite $Limite"
$HealthArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$HealthScript`" -NombreServicio `"$NombreServicio`" -RestartOnFailure"

if ($Uninstall) {
    Write-Output "[PRB-108] Desinstalando '$NombreServicio' (modo=$ModoEfectivo, dryRun=$DryRun)..."
    if ($DryRun) {
        Write-Output "[DRY-RUN] Detendría y eliminaría servicio/tarea '$NombreServicio' y monitor '$TaskMonitorName'."
        exit 0
    }
    if ($ModoEfectivo -eq "NSSM") {
        & $NssmExe stop $NombreServicio 2>$null | Out-Null
        & $NssmExe remove $NombreServicio confirm
    } else {
        Unregister-ScheduledTask -TaskName $NombreServicio -Confirm:$false -ErrorAction SilentlyContinue
    }
    Unregister-ScheduledTask -TaskName $TaskMonitorName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "[PRB-108] Servicio y monitor eliminados correctamente."
    exit 0
}

Write-Output "[PRB-108] Configuración de despliegue:"
Write-Output "  - Nombre: $NombreServicio"
Write-Output "  - Modo:   $ModoEfectivo"
Write-Output "  - Repo:   $RepoRoot"
Write-Output "  - Logs:   $LogDir (rotación 5 MB x 5 archivos)"
Write-Output "  - Cmd:    $PsExe $RunnerArgs"

if ($DryRun) {
    Write-Output "[DRY-RUN] Validación completada sin modificar servicios ni tareas de Windows."
    exit 0
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

if ($ModoEfectivo -eq "NSSM") {
    & $NssmExe install $NombreServicio $PsExe $RunnerArgs
    & $NssmExe set $NombreServicio AppDirectory $RepoRoot
    & $NssmExe set $NombreServicio DisplayName "Cevichería La Casa Blanca - Worker Impresión 80mm"
    & $NssmExe set $NombreServicio Description "Despacha en segundo plano la cola ESC/POS (PRB-58/PRB-107/PRB-108)."
    & $NssmExe set $NombreServicio Start SERVICE_AUTO_START
    & $NssmExe set $NombreServicio AppExit Default Restart
    & $NssmExe set $NombreServicio AppRestartDelay 5000
    & $NssmExe set $NombreServicio AppStdout (Join-Path $LogDir "service_stdout.log")
    & $NssmExe set $NombreServicio AppStderr (Join-Path $LogDir "service_stderr.log")
    & $NssmExe set $NombreServicio AppRotateFiles 1
    & $NssmExe set $NombreServicio AppRotateOnline 1
    & $NssmExe set $NombreServicio AppRotateBytes 5242880
    & $NssmExe start $NombreServicio
    Write-Output "[PRB-108] Servicio NSSM '$NombreServicio' instalado e iniciado."
} else {
    $Action = New-ScheduledTaskAction -Execute $PsExe -Argument $RunnerArgs -WorkingDirectory $RepoRoot
    $Trigger = New-ScheduledTaskTrigger -AtStartup
    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
        -MultipleInstances IgnoreNew
    $Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask `
        -TaskName $NombreServicio `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "Worker de impresión térmica 80 mm para Cevichería La Casa Blanca (PRB-108)." `
        -Force | Out-Null
    Start-ScheduledTask -TaskName $NombreServicio
    Write-Output "[PRB-108] Tarea Programada '$NombreServicio' registrada (AtStartup + auto-reinicio) e iniciada."
}

# Monitor periódico cada 5 minutos para verificar heartbeat y reiniciar si se detuvo
$MonAction = New-ScheduledTaskAction -Execute $PsExe -Argument $HealthArgs -WorkingDirectory $RepoRoot
$MonTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$MonSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable
$MonPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask `
    -TaskName $TaskMonitorName `
    -Action $MonAction `
    -Trigger $MonTrigger `
    -Settings $MonSettings `
    -Principal $MonPrincipal `
    -Description "Healthcheck y autorecuperación cada 5 min del worker de impresión (PRB-108)." `
    -Force | Out-Null

Write-Output "[PRB-108] Monitor '$TaskMonitorName' registrado (cada 5 minutos)."
