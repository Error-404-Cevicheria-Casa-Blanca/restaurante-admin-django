"""Migración idempotente y auditoría de datos reales de producción (PRB-52 / P-04).

Alinea carta marina oficial (15 platos con precios y fotos PNG locales),
distribución de 13 mesas (Piso 1 y Piso 2), roles canónicos y cuentas operativas
con hashes BCrypt cost 10 en `clave_hash` y `pin_hash` (Regla D7 y Regla D8).
"""

from datetime import time
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction

from .models import (
    Categoria,
    DetallePedido,
    Mesa,
    Pago,
    Pedido,
    Producto,
    Rol,
    SesionCaja,
    Terminal,
    Turno,
    Usuario,
)
from .sqlite_bootstrap import asegurar_tablas_sqlite

HASH_DEBIL_DEMO = "$2b$10$b5o6bC2KfOaSLwhhC8UEjuD1ySzwScC7ZuSj82CCM6PYI4iNyQJ0S"

ROLES_OFICIALES = ("ADMIN", "MOZO", "COCINERO", "CAJERO")

USUARIOS_PRODUCCION = (
    {
        "username": "admin_casablanca",
        "rol": "ADMIN",
        "clave_hash": "$2b$10$DKEHgzLn6shfGj/CuZTVR.UM5yPWvDNcG3xmqm1fvHrvzq6eEMUnW",
        "pin_hash": "$2b$10$nCEbqb1gjv2B9gH3BjYxhuYak2QeZcowFaNx1ecAo1ObCSuSu0og2",
    },
    {
        "username": "cajero_01",
        "rol": "CAJERO",
        "clave_hash": "$2b$10$q4uxzvPmonj4yAazKZTf9uRQzHhaOfREQBXIRzt0OZO.hlfAPrd/K",
        "pin_hash": "$2b$10$2am1ckanDtp87GRVfMnI7.Cs5rzqp1UxnL0ZDbxVyDF1SYpn2BNRi",
    },
    {
        "username": "mozo_01",
        "rol": "MOZO",
        "clave_hash": "$2b$10$xPju1s2hMHa4jMUhW.vzCOT8Jxj7JeLs42H6DA73biyIBZXhBIXXO",
        "pin_hash": "$2b$10$GfpUH9Hzg3yIwfN81Rb5bOBBlsFwpWU/TjBIkDZOZCyhWDPGYj0F.",
    },
    {
        "username": "mozo_02",
        "rol": "MOZO",
        "clave_hash": "$2b$10$UdxWr.j7CveWqsLii4ohOeO4WJJVJRv.GHRvsier6SRf8aCZoc2la",
        "pin_hash": "$2b$10$/AzYAZN9wyMUOQO.jiaCmOa.LJFVNw52q.eBLel.5gmxj0x2i4suC",
    },
    {
        "username": "cocinero_01",
        "rol": "COCINERO",
        "clave_hash": "$2b$10$4LKw5u8HgC/DRp0t6It8beUPuY9PO/hUkphPwcuC16/qkMdo0TAAC",
        "pin_hash": "$2b$10$PLWdrtnbLZwZPumxGKSVLOPWIL.9aGcri2VPaO9ztWRlFyxpZ4sd2",
    },
)

PLATOS_DEMO_OBSOLETOS = (
    "Ceviche Clásico",
    "Leche de Tigre",
    "Jalea Mixta",
    "Chicha Morada",
)

CARTA_PRODUCCION = (
    (
        "Entradas Marinas",
        (
            (
                "Leche de Tigre Clásica",
                "Concentrado cítrico de pescado del día con cancha chulpi y choclo.",
                Decimal("25.00"),
                "/static/catalogo/img/platos/leche_tigre.png",
            ),
            (
                "Causa de Pulpa de Cangrejo",
                "Masa de papa amarilla al ají amarillo rellena de pulpa de cangrejo.",
                Decimal("32.00"),
                "/static/catalogo/img/platos/causa_cangrejo.png",
            ),
            (
                "Choros a la Chalaca",
                "Media docena de choros con zarza criolla, choclo tierno y limón.",
                Decimal("24.00"),
                "/static/catalogo/img/platos/choros_chalaca.png",
            ),
        ),
    ),
    (
        "Ceviches y Tiraditos",
        (
            (
                "Ceviche Clásico Casa Blanca",
                "Pesca blanca del día marinada al instante en limón sutil y ají limo.",
                Decimal("48.00"),
                "/static/catalogo/img/platos/ceviche_clasico.png",
            ),
            (
                "Ceviche Mixto Especial",
                "Pescado del día, langostinos, pulpo y calamar con camote glaseado.",
                Decimal("54.00"),
                "/static/catalogo/img/platos/ceviche_mixto.png",
            ),
            (
                "Tiradito en Crema de Ají Amarillo",
                "Láminas de corvina fresca bañadas en emulsión suave de ají amarillo.",
                Decimal("49.00"),
                "/static/catalogo/img/platos/tiradito_aji.png",
            ),
            (
                "Ceviche de Conchas Negras",
                "Conchas negras de Tumbes con cebolla roja, culantro y limón.",
                Decimal("56.00"),
                "/static/catalogo/img/platos/conchas_negras.png",
            ),
        ),
    ),
    (
        "Platos de Fondo",
        (
            (
                "Jalea Mixta Real",
                "Chicharrón crujiente de pescado y mariscos con yucas doradas y tártara.",
                Decimal("58.00"),
                "/static/catalogo/img/platos/jalea_mixta.png",
            ),
            (
                "Arroz con Mariscos",
                "Arroz norteño al culantro y coral con mariscos seleccionados.",
                Decimal("50.00"),
                "/static/catalogo/img/platos/arroz_mariscos.png",
            ),
            (
                "Parihuela Concentrada",
                "Sudado tradicional de cabrilla, cangrejo y mariscos al vino blanco.",
                Decimal("55.00"),
                "/static/catalogo/img/platos/parihuela.png",
            ),
            (
                "Corvina a lo Macho",
                "Filete de corvina a la plancha en salsa cremosa de mariscos.",
                Decimal("62.00"),
                "/static/catalogo/img/platos/corvina_macho.png",
            ),
        ),
    ),
    (
        "Bebidas",
        (
            (
                "Chicha Morada de la Casa (1 L)",
                "Jarra de maíz morado hervido con piña, membrillo, canela y clavo.",
                Decimal("16.00"),
                "/static/catalogo/img/platos/chicha_morada.png",
            ),
            (
                "Limonada Frozen (1 L)",
                "Jarra refrescante de limón sutil recién exprimido.",
                Decimal("18.00"),
                "/static/catalogo/img/platos/limonada_frozen.png",
            ),
        ),
    ),
    (
        "Postres",
        (
            (
                "Suspiro a la Limeña",
                "Manjar de yemas perfumado al oporto con merengue italiano.",
                Decimal("14.00"),
                "/static/catalogo/img/platos/suspiro_limena.png",
            ),
            (
                "Picarones con Miel de Chancaca",
                "Porción tradicional de zapallo y camote con miel de higo.",
                Decimal("15.00"),
                "/static/catalogo/img/platos/picarones.png",
            ),
        ),
    ),
)

MESAS_PRODUCCION = (
    (1, 4, "Primer piso - Salón"),
    (2, 4, "Primer piso - Salón"),
    (3, 4, "Primer piso - Salón"),
    (4, 6, "Primer piso - Familiar"),
    (5, 6, "Primer piso - Familiar"),
    (6, 2, "Primer piso - Barra Marina"),
    (7, 2, "Primer piso - Barra Marina"),
    (8, 4, "Segundo piso - Salón"),
    (9, 4, "Segundo piso - Salón"),
    (10, 4, "Segundo piso - Salón"),
    (11, 6, "Segundo piso - Vista Mar"),
    (12, 6, "Segundo piso - Vista Mar"),
    (13, 8, "Segundo piso - Terraza VIP"),
)

TURNOS_PRODUCCION = (
    ("Mañana", time(8, 0), time(16, 0), True),
    ("Tarde", time(16, 0), time(23, 30), True),
)

TERMINALES_PRODUCCION = (
    ("TERM-01", "Tablet Salón Principal", True),
    ("TERM-02", "Tablet Segundo Piso / Terraza", True),
)


def cargar_datos_produccion():
    """Ejecuta de forma transaccional e idempotente la carga oficial PRB-52."""
    asegurar_tablas_sqlite()

    with transaction.atomic():
        # 1. Roles oficiales
        mapa_roles = {}
        roles_creados = 0
        for nombre_rol in ROLES_OFICIALES:
            rol_obj, creado = Rol.objects.get_or_create(nombre=nombre_rol)
            mapa_roles[nombre_rol] = rol_obj
            if creado:
                roles_creados += 1

        # 2. Saneamiento de admin_test y alta/actualización de usuarios con PIN BCrypt
        admin_demo = Usuario.objects.filter(username="admin_test").first()
        if admin_demo is not None:
            en_uso = (
                Pedido.objects.filter(mozo_id=admin_demo.id).exists()
                or Mesa.objects.filter(mozo_id=admin_demo.id).exists()
                or SesionCaja.objects.filter(cajero_id=admin_demo.id).exists()
                or Pago.objects.filter(mozo_id=admin_demo.id).exists()
            )
            if not en_uso:
                admin_demo.delete()
            elif admin_demo.clave_hash == HASH_DEBIL_DEMO:
                admin_demo.clave_hash = USUARIOS_PRODUCCION[0]["clave_hash"]
                if not admin_demo.tiene_pin:
                    admin_demo.pin_hash = USUARIOS_PRODUCCION[0]["pin_hash"]
                admin_demo.save(update_fields=["clave_hash", "pin_hash"])

        usuarios_creados = 0
        usuarios_actualizados = 0
        for spec in USUARIOS_PRODUCCION:
            rol_obj = mapa_roles[spec["rol"]]
            usr, creado = Usuario.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "rol": rol_obj,
                    "clave_hash": spec["clave_hash"],
                    "pin_hash": spec["pin_hash"],
                    "intentos_fallidos": 0,
                    "bloqueado_hasta": None,
                },
            )
            if creado:
                usuarios_creados += 1
            else:
                campos = []
                if usr.rol_id != rol_obj.id:
                    usr.rol = rol_obj
                    campos.append("rol")
                if not usr.clave_hash or usr.clave_hash == HASH_DEBIL_DEMO:
                    usr.clave_hash = spec["clave_hash"]
                    campos.append("clave_hash")
                if not usr.tiene_pin:
                    usr.pin_hash = spec["pin_hash"]
                    campos.append("pin_hash")
                if campos:
                    usr.save(update_fields=campos)
                    usuarios_actualizados += 1

        # 3. Categorías oficiales y retiro seguro de platos demo obsoletos
        mapa_categorias = {}
        categorias_creadas = 0
        for nombre_cat, _ in CARTA_PRODUCCION:
            cat_obj, creada = Categoria.objects.get_or_create(nombre=nombre_cat)
            mapa_categorias[nombre_cat] = cat_obj
            if creada:
                categorias_creadas += 1

        ids_con_comandas = set(
            DetallePedido.objects.filter(
                producto__nombre__in=PLATOS_DEMO_OBSOLETOS
            ).values_list("producto_id", flat=True)
        )
        Producto.objects.filter(nombre__in=PLATOS_DEMO_OBSOLETOS).exclude(
            id__in=ids_con_comandas
        ).delete()
        if ids_con_comandas:
            Producto.objects.filter(id__in=ids_con_comandas).update(
                disponible=False,
                categoria=mapa_categorias["Entradas Marinas"],
            )
        Categoria.objects.filter(nombre="Entradas", productos__isnull=True).delete()

        # 4. Carta oficial de 15 platos con precios verificados e imagen local
        platos_creados = 0
        platos_actualizados = 0
        for nombre_cat, platos in CARTA_PRODUCCION:
            cat_obj = mapa_categorias[nombre_cat]
            for nombre_plato, descripcion, precio, imagen_url in platos:
                plato_obj, creado = Producto.objects.get_or_create(
                    nombre=nombre_plato,
                    defaults={
                        "descripcion": descripcion,
                        "precio": precio,
                        "disponible": True,
                        "categoria": cat_obj,
                        "imagen_url": imagen_url,
                    },
                )
                if creado:
                    platos_creados += 1
                else:
                    campos_p = []
                    if plato_obj.descripcion != descripcion:
                        plato_obj.descripcion = descripcion
                        campos_p.append("descripcion")
                    if plato_obj.precio != precio:
                        plato_obj.precio = precio
                        campos_p.append("precio")
                    if plato_obj.categoria_id != cat_obj.id:
                        plato_obj.categoria = cat_obj
                        campos_p.append("categoria")
                    if plato_obj.imagen_url != imagen_url:
                        plato_obj.imagen_url = imagen_url
                        campos_p.append("imagen_url")
                    if campos_p:
                        plato_obj.save(update_fields=campos_p)
                        platos_actualizados += 1

        # 5. Las 13 mesas reales (sin pisar estado operativo activo)
        mesas_creadas = 0
        mesas_actualizadas = 0
        for numero, capacidad, ubicacion in MESAS_PRODUCCION:
            mesa_obj, creada = Mesa.objects.get_or_create(
                numero=numero,
                defaults={
                    "capacidad": capacidad,
                    "ubicacion": ubicacion,
                    "estado": Mesa.ESTADO_LIBRE,
                },
            )
            if creada:
                mesas_creadas += 1
            elif mesa_obj.capacidad != capacidad or mesa_obj.ubicacion != ubicacion:
                mesa_obj.capacidad = capacidad
                mesa_obj.ubicacion = ubicacion
                mesa_obj.save(update_fields=["capacidad", "ubicacion"])
                mesas_actualizadas += 1

        # 6. Turnos de salón y terminales POS oficiales (PRB-84)
        turnos_creados = 0
        for nombre_turno, hora_ini, hora_fin, activo in TURNOS_PRODUCCION:
            turno_obj, creado = Turno.objects.get_or_create(
                nombre=nombre_turno,
                defaults={
                    "hora_inicio": hora_ini,
                    "hora_fin": hora_fin,
                    "activo": activo,
                },
            )
            if creado:
                turnos_creados += 1
            elif (
                turno_obj.hora_inicio != hora_ini
                or turno_obj.hora_fin != hora_fin
                or turno_obj.activo != activo
            ):
                turno_obj.hora_inicio = hora_ini
                turno_obj.hora_fin = hora_fin
                turno_obj.activo = activo
                turno_obj.save(update_fields=["hora_inicio", "hora_fin", "activo"])

        terminales_creadas = 0
        for codigo_term, nombre_term, activo in TERMINALES_PRODUCCION:
            term_obj, creada = Terminal.objects.get_or_create(
                codigo=codigo_term,
                defaults={"nombre": nombre_term, "activo": activo},
            )
            if creada:
                terminales_creadas += 1
            elif term_obj.nombre != nombre_term or term_obj.activo != activo:
                term_obj.nombre = nombre_term
                term_obj.activo = activo
                term_obj.save(update_fields=["nombre", "activo"])

    return {
        "roles_creados": roles_creados,
        "usuarios_creados": usuarios_creados,
        "usuarios_actualizados": usuarios_actualizados,
        "categorias_creadas": categorias_creadas,
        "platos_creados": platos_creados,
        "platos_actualizados": platos_actualizados,
        "mesas_creadas": mesas_creadas,
        "mesas_actualizadas": mesas_actualizadas,
        "turnos_creados": turnos_creados,
        "terminales_creadas": terminales_creadas,
    }


def auditar_datos_produccion():
    """Verifica la completitud e integridad de los datos de producción (PRB-52)."""
    asegurar_tablas_sqlite()
    errores = []

    roles_db = set(Rol.objects.values_list("nombre", flat=True))
    faltan_roles = set(ROLES_OFICIALES) - roles_db
    if faltan_roles:
        errores.append(f"Faltan roles canónicos: {sorted(faltan_roles)}")

    if Usuario.objects.filter(clave_hash=HASH_DEBIL_DEMO).exists():
        errores.append(
            "Existen cuentas operativas con el hash débil de demostración (password123)."
        )

    for spec in USUARIOS_PRODUCCION:
        u = Usuario.objects.filter(username=spec["username"]).first()
        if u is None:
            errores.append(f"Falta usuario operativo '{spec['username']}'.")
            continue
        if not u.clave_hash.startswith(("$2b$10$", "$2a$10$")):
            errores.append(
                f"Usuario '{u.username}' no tiene clave_hash BCrypt cost 10."
            )
        if not u.tiene_pin:
            errores.append(
                f"Usuario '{u.username}' carece de pin_hash BCrypt registrado."
            )

    static_root = Path(settings.BASE_DIR) / "catalogo" / "static"
    nombres_oficiales = []
    for _, platos in CARTA_PRODUCCION:
        for nombre_plato, _, precio_esp, img_url in platos:
            nombres_oficiales.append(nombre_plato)
            p = Producto.objects.filter(nombre=nombre_plato).first()
            if p is None:
                errores.append(f"Falta plato oficial '{nombre_plato}'.")
                continue
            if p.precio != precio_esp:
                errores.append(
                    f"Precio desalineado en '{nombre_plato}': {p.precio} != {precio_esp}."
                )
            if not p.imagen_url:
                errores.append(f"Plato '{nombre_plato}' no tiene imagen_url.")
            elif p.imagen_url.startswith("/static/"):
                rel = p.imagen_url.removeprefix("/static/")
                if not (static_root / rel).is_file():
                    errores.append(
                        f"Archivo de foto inexistente para '{nombre_plato}': {rel}"
                    )

    numeros_mesas = set(Mesa.objects.values_list("numero", flat=True))
    esperadas = {m[0] for m in MESAS_PRODUCCION}
    if not esperadas.issubset(numeros_mesas):
        errores.append(f"Faltan mesas oficiales: {sorted(esperadas - numeros_mesas)}")

    turnos_db = set(Turno.objects.values_list("nombre", flat=True))
    turnos_esperados = {t[0] for t in TURNOS_PRODUCCION}
    if not turnos_esperados.issubset(turnos_db):
        errores.append(
            f"Faltan turnos oficiales: {sorted(turnos_esperados - turnos_db)}"
        )

    terminales_db = set(Terminal.objects.values_list("codigo", flat=True))
    terminales_esperadas = {t[0] for t in TERMINALES_PRODUCCION}
    if not terminales_esperadas.issubset(terminales_db):
        errores.append(
            f"Faltan terminales oficiales: {sorted(terminales_esperadas - terminales_db)}"
        )

    return {
        "ok": len(errores) == 0,
        "errores": errores,
        "roles_total": Rol.objects.count(),
        "usuarios_con_pin": Usuario.objects.exclude(pin_hash__isnull=True)
        .exclude(pin_hash="")
        .count(),
        "platos_oficiales": Producto.objects.filter(
            nombre__in=nombres_oficiales
        ).count(),
        "mesas_total": Mesa.objects.filter(numero__in=esperadas).count(),
        "turnos_total": Turno.objects.filter(nombre__in=turnos_esperados).count(),
        "terminales_total": Terminal.objects.filter(
            codigo__in=terminales_esperadas
        ).count(),
    }
