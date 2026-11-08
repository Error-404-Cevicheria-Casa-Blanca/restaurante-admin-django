@echo off
title Django La Casa Blanca - PostgreSQL: casablanca (Port 8000)
color 0B
cd /d C:\Users\LOQ\Documents\restaurante-admin-django

:: Variables de conexion a PostgreSQL
if "%DB_NAME%"=="" set DB_NAME=casablanca
if "%DB_USER%"=="" set DB_USER=postgres
if "%DB_PASSWORD%"=="" set /p DB_PASSWORD="Ingrese DB_PASSWORD: "
if "%DB_HOST%"=="" set DB_HOST=localhost
if "%DB_PORT%"=="" set DB_PORT=5432

:: Variables de Django
set DJANGO_DEBUG=1
set DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

echo ===================================================================
echo   CONECTADO A POSTGRESQL: casablanca @ localhost:5432
echo   INICIANDO SERVIDOR DJANGO - CEVICHERIA LA CASA BLANCA
echo ===================================================================
venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
pause
