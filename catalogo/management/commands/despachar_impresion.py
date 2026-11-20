"""Worker de despacho de cola térmica ESC/POS 80 mm (PRB-107 / PRB-108).

Uso típico:
    python manage.py despachar_impresion --once
    python manage.py despachar_impresion --loop --intervalo 2 --log-file logs/impresion/worker.log
    python manage.py despachar_impresion --healthcheck --health-file logs/impresion/health.json
"""

from datetime import datetime, timezone as dt_timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from catalogo.impresion_service import (
    despachar_cola_pendientes,
    obtener_config_impresora,
)
from catalogo.models import ImpresionCola


def _configurar_logger(log_file=None, max_bytes=5 * 1024 * 1024, backups=5):
    """Configura un logger dedicado con rotación de archivo cuando se indica log_file."""
    logger = logging.getLogger("catalogo.impresion.worker")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = None
    if log_file:
        ruta = Path(log_file)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            str(ruta),
            maxBytes=max_bytes,
            backupCount=backups,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger, handler


def _escribir_heartbeat(health_file, payload):
    """Escribe el archivo JSON de heartbeat de forma atómica."""
    if not health_file:
        return
    ruta = Path(health_file)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, ruta)


def verificar_health_file(health_file, max_age_seconds=30):
    """Valida que el archivo de healthcheck exista, esté sano y actualizado."""
    if not health_file:
        raise CommandError("Debes indicar --health-file para ejecutar --healthcheck.")

    ruta = Path(health_file)
    if not ruta.exists():
        raise CommandError(f"Healthcheck fallido: no existe {ruta}.")

    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CommandError(f"Healthcheck fallido: JSON inválido en {ruta}: {exc}") from exc

    status = str(data.get("status", "")).lower()
    ts_raw = data.get("timestamp_utc")
    if not ts_raw:
        raise CommandError("Healthcheck fallido: falta timestamp_utc en el heartbeat.")

    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CommandError(f"Healthcheck fallido: timestamp inválido ({ts_raw}).") from exc

    ahora = datetime.now(dt_timezone.utc)
    edad = (ahora - ts).total_seconds()
    if edad > max_age_seconds:
        raise CommandError(
            f"Healthcheck fallido: heartbeat obsoleto ({edad:.1f}s > {max_age_seconds}s)."
        )

    if status != "ok":
        ultimo_error = data.get("ultimo_error") or "estado degradado"
        raise CommandError(
            f"Healthcheck fallido: estado={status} ({ultimo_error})."
        )

    return data, edad


class Command(BaseCommand):
    help = (
        "Procesa la cola 'impresion_cola' en estado PENDIENTE generando bytes ESC/POS "
        "de comandas y pre-cuentas con control de reintentos (--once, --loop, --healthcheck)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Ejecuta un único ciclo FIFO de despacho y termina.",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Mantiene el worker en ejecución continua despachando trabajos pendientes.",
        )
        parser.add_argument(
            "--healthcheck",
            action="store_true",
            help="Valida el archivo de heartbeat (--health-file) y retorna código 0 o 1.",
        )
        parser.add_argument(
            "--intervalo",
            type=float,
            default=2.0,
            help="Segundos de espera entre ciclos en modo --loop (por defecto: 2.0).",
        )
        parser.add_argument(
            "--limite",
            type=int,
            default=20,
            help="Máximo de trabajos PENDIENTE a procesar por ciclo (por defecto: 20).",
        )
        parser.add_argument(
            "--max-ciclos",
            type=int,
            default=0,
            help="Límite de ciclos en --loop (0 = infinito; útil para pruebas).",
        )
        parser.add_argument(
            "--modo",
            type=str,
            choices=["NETWORK", "DUMMY", "FAIL_SIMULATED"],
            default=None,
            help="Sobrescribe PRINTER_MODE para esta ejecución.",
        )
        parser.add_argument(
            "--host",
            type=str,
            default=None,
            help="Sobrescribe PRINTER_HOST para esta ejecución.",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=None,
            help="Sobrescribe PRINTER_PORT para esta ejecución.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=None,
            help="Sobrescribe PRINTER_TIMEOUT en segundos.",
        )
        parser.add_argument(
            "--log-file",
            type=str,
            default=None,
            help="Ruta del archivo de log rotativo (UTF-8).",
        )
        parser.add_argument(
            "--log-max-bytes",
            type=int,
            default=5 * 1024 * 1024,
            help="Tamaño máximo por archivo de log antes de rotar (default: 5 MB).",
        )
        parser.add_argument(
            "--log-backups",
            type=int,
            default=5,
            help="Cantidad de archivos de respaldo al rotar logs (default: 5).",
        )
        parser.add_argument(
            "--health-file",
            type=str,
            default=None,
            help="Ruta del archivo JSON de heartbeat/healthcheck.",
        )
        parser.add_argument(
            "--max-age-seconds",
            type=int,
            default=30,
            help="Edad máxima permitida del heartbeat en --healthcheck (default: 30s).",
        )

    def _emitir(self, logger, mensaje, level="info", style_fn=None):
        if style_fn:
            self.stdout.write(style_fn(mensaje))
        else:
            self.stdout.write(mensaje)
        if logger.handlers:
            getattr(logger, level)(mensaje)

    def _ejecutar_ciclo(self, options, cfg, logger):
        resultados = despachar_cola_pendientes(
            limite=options["limite"],
            modo=options["modo"],
            host=options["host"],
            port=options["port"],
            timeout=options["timeout"],
        )
        impresos = sum(1 for r in resultados if r["exito"])
        fallidos_ciclo = sum(1 for r in resultados if not r["exito"])
        for res in resultados:
            estado = res.get("estado") or "?"
            tipo = res.get("tipo") or "TRABAJO"
            intentos = res.get("intentos") or 0
            msg = (
                f"Trabajo #{res['id']} [{tipo}] -> {estado} "
                f"(intento {intentos}): {res['mensaje']}"
            )
            if res["exito"]:
                self._emitir(logger, msg, level="info", style_fn=self.style.SUCCESS)
            else:
                self._emitir(logger, msg, level="warning", style_fn=self.style.WARNING)
        return len(resultados), impresos, fallidos_ciclo

    def handle(self, *args, **options):
        if options["healthcheck"]:
            data, edad = verificar_health_file(
                options["health_file"],
                max_age_seconds=options["max_age_seconds"],
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"HEALTHY | pid={data.get('pid')} | modo={data.get('modo')} | "
                    f"ciclos={data.get('ciclos')} | edad={edad:.1f}s | "
                    f"pendientes={data.get('pendientes_en_cola')}"
                )
            )
            return

        if options["once"] and options["loop"]:
            raise CommandError("No puedes combinar --once y --loop en la misma ejecución.")

        if options["intervalo"] <= 0:
            raise CommandError("--intervalo debe ser mayor a 0.")

        if options["limite"] <= 0:
            raise CommandError("--limite debe ser mayor a 0.")

        modo_loop = bool(options["loop"])
        cfg = obtener_config_impresora(
            host=options["host"],
            port=options["port"],
            timeout=options["timeout"],
            modo=options["modo"],
        )
        logger, file_handler = _configurar_logger(
            log_file=options["log_file"],
            max_bytes=options["log_max_bytes"],
            backups=options["log_backups"],
        )

        detener = {"flag": False}

        def _manejar_senal(signum, _frame):
            detener["flag"] = True
            self._emitir(
                logger,
                f"Señal {signum} recibida; finalizando worker de impresión...",
                level="info",
            )

        prev_sigterm = None
        if modo_loop and hasattr(signal, "SIGTERM"):
            try:
                prev_sigterm = signal.signal(signal.SIGTERM, _manejar_senal)
            except ValueError:
                prev_sigterm = None

        ciclos = 0
        procesados_total = 0
        impresos_total = 0
        fallidos_total = 0

        self._emitir(
            logger,
            (
                f"Worker despachar_impresion iniciado "
                f"(ejecucion={'loop' if modo_loop else 'once'}, "
                f"modo={cfg['modo']}, destino={cfg['host']}:{cfg['port']}, "
                f"limite={options['limite']})."
            ),
            level="info",
        )

        try:
            while not detener["flag"]:
                ciclos += 1
                ultimo_error = None
                status = "ok"
                pendientes_restantes = 0
                try:
                    if modo_loop:
                        close_old_connections()
                    proc, imp, fall = self._ejecutar_ciclo(options, cfg, logger)
                    procesados_total += proc
                    impresos_total += imp
                    fallidos_total += fall
                    pendientes_restantes = ImpresionCola.objects.filter(
                        estado=ImpresionCola.ESTADO_PENDIENTE
                    ).count()
                except Exception as exc:
                    status = "degraded"
                    ultimo_error = str(exc)
                    self._emitir(
                        logger,
                        f"Error en ciclo #{ciclos} del worker: {exc}",
                        level="error",
                        style_fn=self.style.ERROR,
                    )
                    if not modo_loop:
                        _escribir_heartbeat(
                            options["health_file"],
                            {
                                "status": status,
                                "pid": os.getpid(),
                                "timestamp_utc": datetime.now(dt_timezone.utc).isoformat(),
                                "modo": cfg["modo"],
                                "host": cfg["host"],
                                "port": cfg["port"],
                                "ciclos": ciclos,
                                "procesados_total": procesados_total,
                                "impresos_total": impresos_total,
                                "fallidos_total": fallidos_total,
                                "pendientes_en_cola": pendientes_restantes,
                                "ultimo_error": ultimo_error,
                            },
                        )
                        raise

                _escribir_heartbeat(
                    options["health_file"],
                    {
                        "status": status,
                        "pid": os.getpid(),
                        "timestamp_utc": datetime.now(dt_timezone.utc).isoformat(),
                        "modo": cfg["modo"],
                        "host": cfg["host"],
                        "port": cfg["port"],
                        "ciclos": ciclos,
                        "procesados_total": procesados_total,
                        "impresos_total": impresos_total,
                        "fallidos_total": fallidos_total,
                        "pendientes_en_cola": pendientes_restantes,
                        "ultimo_error": ultimo_error,
                    },
                )

                if not modo_loop:
                    break

                max_ciclos = options["max_ciclos"]
                if max_ciclos > 0 and ciclos >= max_ciclos:
                    break

                time.sleep(options["intervalo"])
        except KeyboardInterrupt:
            self._emitir(logger, "Worker detenido por KeyboardInterrupt.", level="info")
        finally:
            if prev_sigterm is not None and hasattr(signal, "SIGTERM"):
                try:
                    signal.signal(signal.SIGTERM, prev_sigterm)
                except ValueError:
                    pass
            self._emitir(
                logger,
                (
                    f"Worker finalizado tras {ciclos} ciclo(s): "
                    f"procesados={procesados_total}, impresos={impresos_total}, "
                    f"reintentos_o_fallos={fallidos_total}."
                ),
                level="info",
            )
            if file_handler:
                logger.removeHandler(file_handler)
                file_handler.close()
