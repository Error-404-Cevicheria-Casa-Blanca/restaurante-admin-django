@echo off
title Django La Casa Blanca - PostgreSQL: casablanca (Port 8000)
color 0B
cd /d "%~dp0"

:: Variables de conexion a PostgreSQL (DB_PASSWORD debe venir del entorno)
if "%DB_NAME%"=="" set DB_NAME=casablanca
if "%DB_USER%"=="" set DB_USER=postgres
if "%DB_HOST%"=="" set DB_HOST=localhost
if "%DB_PORT%"=="" set DB_PORT=5432

if "%DB_PASSWORD%"=="" (
    echo [ERROR] Debe definir la variable de entorno DB_PASSWORD antes de ejecutar este script.
    exit /b 1
)

:: Variables de Django
set DJANGO_DEBUG=1
set DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

echo ===================================================================
echo   CONECTADO A POSTGRESQL: %DB_NAME% @ %DB_HOST%:%DB_PORT%
echo   INICIANDO SERVIDOR DJANGO - CEVICHERIA LA CASA BLANCA
echo ===================================================================
venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
pause
