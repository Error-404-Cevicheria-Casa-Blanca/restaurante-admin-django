@echo off
title Django La Casa Blanca - PostgreSQL: casablanca (Port 8000)
color 0B
cd /d C:\Users\LOQ\Documents\restaurante-admin-django

:: Variables de conexion a PostgreSQL
set DB_NAME=casablanca
set DB_USER=postgres
set DB_PASSWORD=Jerardo
set DB_HOST=localhost
set DB_PORT=5432

:: Variables de Django
set DJANGO_DEBUG=1
set DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

echo ===================================================================
echo   CONECTADO A POSTGRESQL: casablanca @ localhost:5432
echo   INICIANDO SERVIDOR DJANGO - CEVICHERIA LA CASA BLANCA
echo ===================================================================
venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
pause
