"""Vistas del módulo web para gestión de catálogo, precios y pesca del día (PRB-19)."""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import Avg, Count, F, Max, Min, ProtectedError, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    AperturaCajaForm,
    CategoriaForm,
    CierreCajaForm,
    ProductoForm,
    UsuarioOperativoForm,
)
from .impresion_service import (
    PRINTER_HOST_DEFAULT,
    PRINTER_MODE_DEFAULT,
    PRINTER_PORT_DEFAULT,
    despachar_cola_pendientes,
    formatear_fecha,
    reimprimir_pedido,
    reintentar_trabajo,
)
from .kds_service import (
    ESTACIONES_INFO,
    avanzar_estado_comanda,
    avanzar_estado_item,
    obtener_comandas_kds,
    resumen_kpis_kds,
    serializar_comandas_json,
)
from .models import (
    Categoria,
    DetallePedido,
    ImpresionCola,
    Mesa,
    MovimientoStock,
    Pago,
    Pedido,
    Producto,
    Rol,
    SesionCaja,
    SesionMozo,
    Terminal,
    Turno,
    Usuario,
)
from .produccion_seeds import (
    ROLES_OFICIALES,
    auditar_datos_produccion,
    cargar_datos_produccion,
)
from .sqlite_bootstrap import asegurar_tablas_sqlite, poblar_carta_ejemplo
from .stock_service import (
    ajustar_stock_producto,
    fijar_stock_diario,
    sincronizar_stock_con_pedidos,
)


def staff_required(view_func):
    """Restringe el acceso a usuarios autenticados con permiso administrativo."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            login_url = reverse("catalogo:login")
            return redirect(f"{login_url}?next={request.get_full_path()}")
        return view_func(request, *args, **kwargs)

    return _wrapped


def _es_peticion_json(request):
    accept = request.headers.get("Accept", "")
    xhr = request.headers.get("X-Requested-With", "")
    return "application/json" in accept or xhr == "XMLHttpRequest"


def _url_retorno_segura(request, fallback_name="catalogo:platos_list"):
    candidata = request.POST.get("next") or request.META.get("HTTP_REFERER")
    if candidata and url_has_allowed_host_and_scheme(
        url=candidata,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidata
    return reverse(fallback_name)


def _resumen_kpis_globales():
    """Calcula métricas reales del catálogo para cabeceras y respuestas AJAX."""
    agregados = Producto.objects.aggregate(
        total=Count("id"),
        disponibles=Count("id", filter=Q(disponible=True)),
        agotados=Count("id", filter=Q(disponible=False)),
        precio_promedio=Avg("precio"),
        precio_min=Min("precio"),
        precio_max=Max("precio"),
    )
    total = agregados["total"] or 0
    disponibles = agregados["disponibles"] or 0
    agotados = agregados["agotados"] or 0
    pct_disponible = round((disponibles / total) * 100, 1) if total else 0.0
    pct_agotado = round((agotados / total) * 100, 1) if total else 0.0
    promedio = agregados["precio_promedio"] or Decimal("0.00")
    minimo = agregados["precio_min"] or Decimal("0.00")
    maximo = agregados["precio_max"] or Decimal("0.00")

    return {
        "total_platos": total,
        "platos_disponibles": disponibles,
        "platos_agotados": agotados,
        "pct_disponibles": pct_disponible,
        "pct_agotados": pct_agotado,
        "precio_promedio": float(round(promedio, 2)),
        "precio_min": float(round(minimo, 2)),
        "precio_max": float(round(maximo, 2)),
    }


def panel_login(request):
    """Inicio de sesión del panel web de gestión de carta."""
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("catalogo:dashboard")

    next_url = request.GET.get("next") or request.POST.get("next") or ""
    error = None

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_active and user.is_staff:
            login(request, user)
            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect("catalogo:dashboard")
        error = "Credenciales inválidas o cuenta sin permisos de administración."

    return render(
        request,
        "catalogo/login.html",
        {"error": error, "next": next_url},
    )


@require_POST
def panel_logout(request):
    """Cierra la sesión administrativa actual."""
    logout(request)
    return redirect("catalogo:login")


@staff_required
def dashboard_catalogo(request):
    """Vista resumen de carta, precios y disponibilidad diaria (PRB-19)."""
    asegurar_tablas_sqlite()

    estado = request.GET.get("estado", "todos")
    categoria_id = request.GET.get("categoria", "")

    categorias_qs = Categoria.objects.annotate(
        total_platos=Count("productos"),
        disponibles=Count("productos", filter=Q(productos__disponible=True)),
        agotados=Count("productos", filter=Q(productos__disponible=False)),
        precio_promedio=Avg("productos__precio"),
        precio_min=Min("productos__precio"),
        precio_max=Max("productos__precio"),
    ).order_by("id")

    productos_qs = Producto.objects.select_related("categoria")
    if estado == "disponibles":
        productos_qs = productos_qs.filter(disponible=True)
    elif estado == "agotados":
        productos_qs = productos_qs.filter(disponible=False)

    categoria_activa = None
    if categoria_id.isdigit():
        categoria_activa = int(categoria_id)
        productos_qs = productos_qs.filter(categoria_id=categoria_activa)

    agregados = productos_qs.aggregate(
        total=Count("id"),
        disponibles=Count("id", filter=Q(disponible=True)),
        agotados=Count("id", filter=Q(disponible=False)),
        precio_promedio=Avg("precio"),
        precio_min=Min("precio"),
        precio_max=Max("precio"),
    )

    total = agregados["total"] or 0
    disponibles = agregados["disponibles"] or 0
    agotados = agregados["agotados"] or 0
    pct_disponibles = round((disponibles / total) * 100, 1) if total else 0.0
    pct_agotados = round((agotados / total) * 100, 1) if total else 0.0
    precio_promedio = agregados["precio_promedio"] or Decimal("0.00")
    precio_min = agregados["precio_min"] or Decimal("0.00")
    precio_max = agregados["precio_max"] or Decimal("0.00")

    categorias_list = list(categorias_qs)
    total_categorias = len(categorias_list)
    categorias_con_stock = sum(1 for c in categorias_list if c.disponibles > 0)
    categorias_sin_agotados = sum(
        1 for c in categorias_list if c.total_platos > 0 and c.agotados == 0
    )

    plato_mayor_precio = productos_qs.order_by("-precio", "nombre").first()
    plato_menor_precio = productos_qs.order_by("precio", "nombre").first()

    chart_categorias = [
        {
            "nombre": cat.nombre,
            "total": cat.total_platos,
            "disponibles": cat.disponibles,
            "agotados": cat.agotados,
            "precio_promedio": float(round(cat.precio_promedio or Decimal("0.00"), 2)),
        }
        for cat in categorias_list
    ]

    chart_donut = {
        "disponibilidad": [
            {"label": "Disponibles hoy", "value": disponibles, "color": "#10b981"},
            {"label": "Agotados (pesca)", "value": agotados, "color": "#f59e0b"},
        ],
        "por_categoria": [
            {"label": cat.nombre, "value": cat.total_platos}
            for cat in categorias_list
            if cat.total_platos > 0
        ],
    }

    platos_destacados = list(
        productos_qs.order_by("-disponible", "categoria__id", "nombre")[:8]
    )

    # Indicadores operativos del día (PRB-45)
    hoy = timezone.localdate()

    total_mesas = Mesa.objects.count()
    mesas_ocupadas = Mesa.objects.filter(
        estado__in=[
            Mesa.ESTADO_OCUPADA,
            Mesa.ESTADO_ATENDIENDO,
            Mesa.ESTADO_ATENDIDA,
        ]
    ).count()
    mesas_libres = Mesa.objects.filter(estado=Mesa.ESTADO_LIBRE).count()
    mesas_pide_cuenta = Mesa.objects.filter(
        estado__in=[Mesa.ESTADO_PIDE_CUENTA, Mesa.ESTADO_CUENTA_SOLICITADA]
    ).count()
    pct_mesas_ocupadas = (
        round((mesas_ocupadas / total_mesas) * 100, 1) if total_mesas else 0.0
    )

    ventas_dia, total_pedidos_cobrados_hoy = _calcular_ventas_y_pedidos_fecha(hoy)

    pedidos_pendientes = Pedido.objects.filter(
        estado__in=[Pedido.ESTADO_PENDIENTE, Pedido.ESTADO_COCINANDO]
    ).count()

    mesas_salon = list(Mesa.objects.all().order_by("numero"))

    pedidos_activos = list(
        Pedido.objects.filter(
            estado__in=[
                Pedido.ESTADO_PENDIENTE,
                Pedido.ESTADO_COCINANDO,
                Pedido.ESTADO_LISTO,
                Pedido.ESTADO_SERVIDO,
            ]
        )
        .select_related("mesa")
        .order_by("-fecha_creacion")[:8]
    )

    context = {
        "nav_active": "dashboard",
        "hoy": hoy,
        "hora_actual": timezone.localtime().strftime("%H:%M:%S"),
        "total_mesas": total_mesas,
        "mesas_ocupadas": mesas_ocupadas,
        "mesas_libres": mesas_libres,
        "mesas_pide_cuenta": mesas_pide_cuenta,
        "pct_mesas_ocupadas": pct_mesas_ocupadas,
        "ventas_dia": ventas_dia,
        "total_pedidos_cobrados_hoy": total_pedidos_cobrados_hoy,
        "pedidos_pendientes": pedidos_pendientes,
        "mesas_salon": mesas_salon,
        "pedidos_activos": pedidos_activos,
        "estado_filtro": estado,
        "categoria_activa": categoria_activa,
        "categorias": categorias_list,
        "total_platos": total,
        "platos_disponibles": disponibles,
        "platos_agotados": agotados,
        "pct_disponibles": pct_disponibles,
        "pct_agotados": pct_agotados,
        "total_categorias": total_categorias,
        "categorias_con_stock": categorias_con_stock,
        "categorias_sin_agotados": categorias_sin_agotados,
        "precio_promedio": precio_promedio,
        "precio_min": precio_min,
        "precio_max": precio_max,
        "plato_mayor_precio": plato_mayor_precio,
        "plato_menor_precio": plato_menor_precio,
        "platos_destacados": platos_destacados,
        "chart_categorias": chart_categorias,
        "chart_donut": chart_donut,
        "form_plato_rapido": ProductoForm(),
    }
    return render(request, "catalogo/dashboard.html", context)


@staff_required
def kpis_operativos_api(request):
    """Devuelve en JSON los 4 indicadores operativos en tiempo real (PRB-45).

    Permite actualización por sondeo simple (polling ligero) sin WebSocket.
    """
    asegurar_tablas_sqlite()
    hoy = timezone.localdate()

    total_mesas = Mesa.objects.count()
    mesas_ocupadas = Mesa.objects.filter(
        estado__in=[
            Mesa.ESTADO_OCUPADA,
            Mesa.ESTADO_ATENDIENDO,
            Mesa.ESTADO_ATENDIDA,
        ]
    ).count()
    mesas_libres = Mesa.objects.filter(estado=Mesa.ESTADO_LIBRE).count()
    mesas_pide_cuenta = Mesa.objects.filter(
        estado__in=[Mesa.ESTADO_PIDE_CUENTA, Mesa.ESTADO_CUENTA_SOLICITADA]
    ).count()
    pct_mesas_ocupadas = (
        round((mesas_ocupadas / total_mesas) * 100, 1) if total_mesas else 0.0
    )

    ventas_dia_dec, total_cobrados = _calcular_ventas_y_pedidos_fecha(hoy)
    ventas_dia = float(ventas_dia_dec)
    platos_agotados = Producto.objects.filter(disponible=False).count()
    pedidos_pendientes = Pedido.objects.filter(
        estado__in=[Pedido.ESTADO_PENDIENTE, Pedido.ESTADO_COCINANDO]
    ).count()

    mesas_data = [
        {
            "id": m.id,
            "numero": m.numero,
            "capacidad": m.capacidad,
            "ubicacion": m.ubicacion,
            "estado": m.estado,
            "estado_display": m.get_estado_display(),
        }
        for m in Mesa.objects.all().order_by("numero")
    ]

    return JsonResponse(
        {
            "ok": True,
            "fecha": hoy.isoformat(),
            "hora": timezone.localtime().strftime("%H:%M:%S"),
            "mesas_ocupadas": mesas_ocupadas,
            "total_mesas": total_mesas,
            "mesas_libres": mesas_libres,
            "mesas_pide_cuenta": mesas_pide_cuenta,
            "pct_mesas_ocupadas": pct_mesas_ocupadas,
            "ventas_dia": f"{ventas_dia:.2f}",
            "pedidos_cobrados_hoy": total_cobrados,
            "platos_agotados": platos_agotados,
            "pedidos_pendientes": pedidos_pendientes,
            "mesas": mesas_data,
        }
    )


@staff_required
def lista_platos(request):
    """Listado filtrable de platos con edición rápida de precios y stock."""
    asegurar_tablas_sqlite()

    busqueda = (request.GET.get("q") or "").strip()
    categoria_id = request.GET.get("categoria", "")
    estado = request.GET.get("estado", "todos")
    orden = request.GET.get("orden", "categoria")

    platos_qs = Producto.objects.select_related("categoria")

    if busqueda:
        platos_qs = platos_qs.filter(
            Q(nombre__icontains=busqueda) | Q(descripcion__icontains=busqueda)
        )
    if categoria_id.isdigit():
        platos_qs = platos_qs.filter(categoria_id=int(categoria_id))
    if estado == "disponibles":
        platos_qs = platos_qs.filter(disponible=True)
    elif estado == "agotados":
        platos_qs = platos_qs.filter(disponible=False)

    mapa_orden = {
        "categoria": ("categoria__id", "nombre"),
        "nombre": ("nombre",),
        "precio_asc": ("precio", "nombre"),
        "precio_desc": ("-precio", "nombre"),
    }
    platos_qs = platos_qs.order_by(*mapa_orden.get(orden, ("categoria__id", "nombre")))

    resumen = _resumen_kpis_globales()
    categorias = Categoria.objects.annotate(total_platos=Count("productos")).order_by(
        "id"
    )

    context = {
        "nav_active": "platos",
        "platos": platos_qs,
        "categorias": categorias,
        "busqueda": busqueda,
        "categoria_activa": int(categoria_id) if categoria_id.isdigit() else None,
        "estado_filtro": estado,
        "orden": orden,
        "total_filtrado": platos_qs.count(),
        "resumen": resumen,
        "form_plato": ProductoForm(),
    }
    return render(request, "catalogo/platos_list.html", context)


@staff_required
def crear_plato(request):
    """Alta de un nuevo plato marino en la carta."""
    asegurar_tablas_sqlite()

    if request.method == "POST":
        form = ProductoForm(request.POST)
        if form.is_valid():
            plato = form.save()
            messages.success(
                request,
                f"Plato «{plato.nombre}» registrado correctamente (S/ {plato.precio}).",
            )
            return redirect(_url_retorno_segura(request, "catalogo:platos_list"))
        messages.error(
            request,
            "Revisa los campos del formulario antes de guardar el plato.",
        )
    else:
        initial = {}
        cat_param = request.GET.get("categoria")
        if cat_param and cat_param.isdigit():
            initial["categoria"] = int(cat_param)
        form = ProductoForm(initial=initial)

    return render(
        request,
        "catalogo/plato_form.html",
        {
            "nav_active": "platos",
            "form": form,
            "modo_edicion": False,
            "categorias_existen": Categoria.objects.exists(),
        },
    )


@staff_required
def editar_plato(request, pk):
    """Edición integral de un plato marino, su precio o disponibilidad."""
    asegurar_tablas_sqlite()
    plato = get_object_or_404(Producto, pk=pk)

    if request.method == "POST":
        form = ProductoForm(request.POST, instance=plato)
        if form.is_valid():
            plato_actualizado = form.save()
            messages.success(
                request,
                f"Plato «{plato_actualizado.nombre}» actualizado con éxito.",
            )
            return redirect("catalogo:platos_list")
        messages.error(request, "Corrige los errores indicados en el formulario.")
    else:
        form = ProductoForm(instance=plato)

    return render(
        request,
        "catalogo/plato_form.html",
        {
            "nav_active": "platos",
            "form": form,
            "plato": plato,
            "modo_edicion": True,
            "categorias_existen": Categoria.objects.exists(),
        },
    )


@staff_required
@require_POST
def eliminar_plato(request, pk):
    """Elimina un plato si no está referenciado por comandas históricas."""
    asegurar_tablas_sqlite()
    plato = get_object_or_404(Producto, pk=pk)
    nombre = plato.nombre
    try:
        plato.delete()
        messages.success(request, f"Plato «{nombre}» eliminado del catálogo.")
    except (ProtectedError, IntegrityError):
        messages.error(
            request,
            f"No se puede eliminar «{nombre}» porque tiene registros asociados. "
            "Márcalo como no disponible en su lugar.",
        )
    return redirect(_url_retorno_segura(request, "catalogo:platos_list"))


@staff_required
@require_POST
def toggle_disponibilidad_plato(request, pk):
    """Activa o desactiva la disponibilidad de un plato según la pesca del día."""
    asegurar_tablas_sqlite()
    plato = get_object_or_404(Producto, pk=pk)

    valor_explicito = request.POST.get("disponible")
    if valor_explicito in ("true", "1", "on"):
        nuevo_disp = True
    elif valor_explicito in ("false", "0", "off"):
        nuevo_disp = False
    else:
        nuevo_disp = not plato.disponible

    if (
        nuevo_disp
        and plato.stock_disponible is not None
        and plato.stock_disponible == 0
    ):
        msg = (
            f"«{plato.nombre}» tiene 0 porciones en el stock del día. "
            "Carga porciones mayores a 0 o pásalo a modo libre para activarlo."
        )
        if _es_peticion_json(request):
            return JsonResponse({"ok": False, "error": msg}, status=409)
        messages.warning(request, msg)
        return redirect(_url_retorno_segura(request, "catalogo:platos_list"))

    plato.disponible = nuevo_disp
    plato.save(update_fields=["disponible"])

    estado_texto = "DISPONIBLE" if plato.disponible else "AGOTADO"
    if _es_peticion_json(request):
        return JsonResponse(
            {
                "ok": True,
                "id": plato.pk,
                "nombre": plato.nombre,
                "disponible": plato.disponible,
                "estado_texto": estado_texto,
                "kpis": _resumen_kpis_globales(),
            }
        )

    messages.success(
        request,
        f"Stock del día actualizado: «{plato.nombre}» ahora está {estado_texto}.",
    )
    return redirect(_url_retorno_segura(request, "catalogo:platos_list"))


@staff_required
@require_POST
def actualizar_precio_plato(request, pk):
    """Actualiza el precio en soles (S/) de un plato de forma rápida."""
    asegurar_tablas_sqlite()
    plato = get_object_or_404(Producto, pk=pk)
    precio_raw = (request.POST.get("precio") or "").replace(",", ".").strip()

    try:
        nuevo_precio = Decimal(precio_raw)
        if not nuevo_precio.is_finite():
            nuevo_precio = None
        else:
            nuevo_precio = nuevo_precio.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
    except (InvalidOperation, ValueError):
        nuevo_precio = None

    if nuevo_precio is None or nuevo_precio <= Decimal("0.00"):
        msg = "El precio debe ser un monto válido mayor a S/ 0.00."
        if _es_peticion_json(request):
            return JsonResponse({"ok": False, "error": msg}, status=400)
        messages.error(request, msg)
        return redirect(_url_retorno_segura(request, "catalogo:platos_list"))

    if nuevo_precio > Decimal("99999999.99"):
        msg = "El precio supera el límite permitido en la carta."
        if _es_peticion_json(request):
            return JsonResponse({"ok": False, "error": msg}, status=400)
        messages.error(request, msg)
        return redirect(_url_retorno_segura(request, "catalogo:platos_list"))

    precio_anterior = plato.precio
    plato.precio = nuevo_precio
    plato.save(update_fields=["precio"])

    if _es_peticion_json(request):
        return JsonResponse(
            {
                "ok": True,
                "id": plato.pk,
                "nombre": plato.nombre,
                "precio": f"{plato.precio:.2f}",
                "precio_anterior": f"{precio_anterior:.2f}",
                "kpis": _resumen_kpis_globales(),
            }
        )

    messages.success(
        request,
        f"Precio de «{plato.nombre}» actualizado a S/ {plato.precio:.2f}.",
    )
    return redirect(_url_retorno_segura(request, "catalogo:platos_list"))


@staff_required
@require_POST
def accion_masiva_platos(request):
    """Ejecuta activación o agotamiento por lote sobre platos seleccionados."""
    asegurar_tablas_sqlite()
    accion = request.POST.get("accion", "")
    ids_raw = request.POST.getlist("plato_ids")
    ids = [int(pk) for pk in ids_raw if pk.isdigit()]

    if not ids:
        messages.warning(
            request, "Selecciona al menos un plato para aplicar el cambio."
        )
        return redirect(_url_retorno_segura(request, "catalogo:platos_list"))

    qs = Producto.objects.filter(pk__in=ids)
    if accion == "marcar_disponible":
        actualizados = qs.exclude(stock_disponible=0).update(disponible=True)
        messages.success(
            request,
            f"{actualizados} plato(s) marcados como DISPONIBLES (pesca del día).",
        )
    elif accion == "marcar_agotado":
        actualizados = qs.update(disponible=False)
        messages.warning(
            request,
            f"{actualizados} plato(s) marcados como AGOTADOS / NO DISPONIBLES.",
        )
    else:
        messages.error(request, "Acción masiva no reconocida.")

    return redirect(_url_retorno_segura(request, "catalogo:platos_list"))


@staff_required
def pesca_del_dia(request):
    """Tablero operativo diario para control rápido de disponibilidad y precios."""
    asegurar_tablas_sqlite()
    _sincronizar_stock_seguro()
    categorias = (
        Categoria.objects.prefetch_related("productos")
        .annotate(
            total_platos=Count("productos"),
            disponibles=Count("productos", filter=Q(productos__disponible=True)),
            agotados=Count("productos", filter=Q(productos__disponible=False)),
        )
        .order_by("id")
    )
    resumen = _resumen_kpis_globales()
    return render(
        request,
        "catalogo/pesca_dia.html",
        {
            "nav_active": "pesca",
            "categorias": categorias,
            "resumen": resumen,
        },
    )


@staff_required
@require_POST
def cambiar_estado_categoria(request, pk):
    """Activa o marca como agotados todos los platos de una categoría marina."""
    asegurar_tablas_sqlite()
    categoria = get_object_or_404(Categoria, pk=pk)
    estado = request.POST.get("estado") == "disponible"
    if estado:
        actualizados = categoria.productos.exclude(stock_disponible=0).update(
            disponible=True
        )
    else:
        actualizados = categoria.productos.update(disponible=False)
    etiqueta = "DISPONIBLES" if estado else "AGOTADOS"
    messages.success(
        request,
        f"{actualizados} plato(s) de «{categoria.nombre}» marcados como {etiqueta}.",
    )
    return redirect(_url_retorno_segura(request, "catalogo:pesca_dia"))


@staff_required
def gestion_categorias(request):
    """Administración de categorías marinas y resumen de platos asociados."""
    asegurar_tablas_sqlite()

    if request.method == "POST":
        form = CategoriaForm(request.POST)
        if form.is_valid():
            cat = form.save()
            messages.success(request, f"Categoría «{cat.nombre}» creada con éxito.")
            return redirect("catalogo:categorias")
        messages.error(request, "No se pudo crear la categoría. Revisa el nombre.")
    else:
        form = CategoriaForm()

    categorias = Categoria.objects.annotate(
        total_platos=Count("productos"),
        disponibles=Count("productos", filter=Q(productos__disponible=True)),
        agotados=Count("productos", filter=Q(productos__disponible=False)),
        precio_promedio=Avg("productos__precio"),
    ).order_by("id")

    return render(
        request,
        "catalogo/categorias.html",
        {
            "nav_active": "categorias",
            "categorias": categorias,
            "form": form,
        },
    )


@staff_required
@require_POST
def editar_categoria(request, pk):
    """Renombra una categoría existente validando unicidad."""
    asegurar_tablas_sqlite()
    categoria = get_object_or_404(Categoria, pk=pk)
    form = CategoriaForm(request.POST, instance=categoria)
    if form.is_valid():
        form.save()
        messages.success(request, f"Categoría actualizada a «{categoria.nombre}».")
    else:
        errores = " ".join(form.errors.get("nombre", ["Nombre inválido."]))
        messages.error(request, errores)
    return redirect("catalogo:categorias")


@staff_required
@require_POST
def eliminar_categoria(request, pk):
    """Elimina una categoría vacía o informa si tiene platos protegidos."""
    asegurar_tablas_sqlite()
    categoria = get_object_or_404(Categoria, pk=pk)
    nombre = categoria.nombre
    if categoria.productos.exists():
        messages.error(
            request,
            f"No se puede eliminar «{nombre}» porque contiene platos registrados.",
        )
        return redirect("catalogo:categorias")

    try:
        categoria.delete()
        messages.success(request, f"Categoría «{nombre}» eliminada correctamente.")
    except (ProtectedError, IntegrityError):
        messages.error(
            request,
            f"No se puede eliminar «{nombre}» porque tiene platos asociados.",
        )
    return redirect("catalogo:categorias")


@staff_required
@require_POST
def cargar_carta_ejemplo_view(request):
    """Carga de forma idempotente platos marinos de demostración."""
    try:
        cat_nuevas, platos_nuevos = poblar_carta_ejemplo()
    except ValueError:
        messages.error(
            request,
            "La carta de ejemplo solo se carga en SQLite. "
            "No se insertaron datos de demostración en la base compartida.",
        )
        return redirect(_url_retorno_segura(request, "catalogo:dashboard"))

    if cat_nuevas or platos_nuevos:
        messages.success(
            request,
            f"Se agregaron {cat_nuevas} categoría(s) y {platos_nuevos} plato(s) marinos.",
        )
    else:
        messages.info(request, "Todos los platos de ejemplo ya estaban en la carta.")
    return redirect(_url_retorno_segura(request, "catalogo:dashboard"))


# =============================================================================
# Cierre de Caja y Arqueo por Turno (PRB-60) y Reportes de Ventas (PRB-61)
# =============================================================================

METODOS_PAGO_ORDEN = [
    (Pago.METODO_EFECTIVO, "Efectivo"),
    (Pago.METODO_YAPE, "Yape"),
    (Pago.METODO_PLIN, "Plin"),
    (Pago.METODO_TARJETA, "Tarjeta"),
]


def _calcular_ventas_y_pedidos_fecha(fecha_consulta):
    """Retorna (total_ventas, pedidos_cobrados) conciliando pagos v2 y comandas."""
    tablas = set(connection.introspection.table_names())
    total_pagos = Decimal("0.00")
    pedidos_con_pago = set()

    if Pago._meta.db_table in tablas:
        pagos_qs = Pago.objects.filter(fecha_pago__date=fecha_consulta)
        total_pagos = pagos_qs.aggregate(s=Sum("monto"))["s"] or Decimal("0.00")
        pedidos_con_pago = set(pagos_qs.values_list("pedido_id", flat=True))

    legacy_qs = Pedido.objects.filter(
        estado=Pedido.ESTADO_COBRADO,
        fecha_creacion__date=fecha_consulta,
    )
    if pedidos_con_pago:
        legacy_qs = legacy_qs.exclude(id__in=pedidos_con_pago)

    legacy_agg = legacy_qs.aggregate(t=Sum("total"), c=Count("id"))
    ventas_legacy = legacy_agg["t"] or Decimal("0.00")
    count_legacy = legacy_agg["c"] or 0

    ventas_totales = (total_pagos + ventas_legacy).quantize(Decimal("0.01"))
    pedidos_totales = len(pedidos_con_pago) + count_legacy
    return ventas_totales, pedidos_totales


def _resolver_cajero_id(user):
    """Resuelve un cajero_id válido respetando la FK a usuario(id) en PostgreSQL."""
    tablas = set(connection.introspection.table_names())
    if "usuario" not in tablas:
        return user.id or 1

    username = (getattr(user, "username", "") or "cajero_panel").strip()
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id FROM usuario WHERE LOWER(username) = LOWER(%s) LIMIT 1",
            [username],
        )
        fila = cur.fetchone()
        if fila:
            return fila[0]

        if "rol" in tablas:
            cur.execute("""
                SELECT u.id
                FROM usuario u
                JOIN rol r ON r.id = u.rol_id
                WHERE r.nombre IN ('CAJERO', 'ADMIN')
                ORDER BY CASE WHEN r.nombre = 'CAJERO' THEN 0 ELSE 1 END, u.id ASC
                LIMIT 1
                """)
            fila = cur.fetchone()
            if fila:
                return fila[0]

        cur.execute("SELECT id FROM usuario ORDER BY id ASC LIMIT 1")
        fila = cur.fetchone()
        if fila:
            return fila[0]

        if "rol" in tablas:
            cur.execute("SELECT id FROM rol WHERE nombre = 'CAJERO' LIMIT 1")
            rol_row = cur.fetchone()
            if rol_row:
                rol_id = rol_row[0]
            else:
                cur.execute("INSERT INTO rol (nombre) VALUES ('CAJERO') RETURNING id")
                rol_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO usuario (username, clave_hash, rol_id) "
                "VALUES (%s, %s, %s) RETURNING id",
                [username[:50], "!django-staff-managed", rol_id],
            )
            return cur.fetchone()[0]

    return user.id or 1


def _mapa_nombres_cajeros(cajero_ids):
    """Devuelve {cajero_id: nombre_legible} consultando usuario o auth_user."""
    ids = {cid for cid in cajero_ids if cid is not None}
    if not ids:
        return {}

    mapa = {}
    tablas = set(connection.introspection.table_names())
    if "usuario" in tablas:
        placeholders = ", ".join(["%s"] * len(ids))
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT id, username FROM usuario WHERE id IN ({placeholders})",
                list(ids),
            )
            for uid, uname in cur.fetchall():
                mapa[uid] = uname

    faltantes = ids - set(mapa.keys())
    if faltantes:
        User = get_user_model()
        for u in User.objects.filter(id__in=faltantes).only("id", "username"):
            mapa[u.id] = u.username

    for cid in ids:
        mapa.setdefault(cid, f"Cajero #{cid}")
    return mapa


def _calcular_resumen_sesion(sesion):
    """Calcula movimientos, totales por medio de pago y monto esperado del turno."""
    pagos_qs = (
        Pago.objects.filter(sesion_caja=sesion)
        .select_related("pedido", "mesa")
        .order_by("-fecha_pago", "-id")
    )
    agregados_metodo = {
        item["metodo"]: {
            "monto": item["monto"] or Decimal("0.00"),
            "propinas": item["propinas"] or Decimal("0.00"),
            "cantidad": item["cantidad"] or 0,
        }
        for item in pagos_qs.values("metodo").annotate(
            monto=Sum("monto"),
            propinas=Sum("propina"),
            cantidad=Count("id"),
        )
    }

    tiene_pagos = bool(agregados_metodo)
    if tiene_pagos:
        efectivo = agregados_metodo.get(Pago.METODO_EFECTIVO, {}).get(
            "monto", Decimal("0.00")
        )
        yape = agregados_metodo.get(Pago.METODO_YAPE, {}).get("monto", Decimal("0.00"))
        plin = agregados_metodo.get(Pago.METODO_PLIN, {}).get("monto", Decimal("0.00"))
        tarjeta = agregados_metodo.get(Pago.METODO_TARJETA, {}).get(
            "monto", Decimal("0.00")
        )
        ventas_digital = (yape + plin + tarjeta).quantize(Decimal("0.01"))
    else:
        efectivo = (sesion.monto_ventas_efectivo or Decimal("0.00")).quantize(
            Decimal("0.01")
        )
        ventas_digital = (sesion.monto_ventas_digital or Decimal("0.00")).quantize(
            Decimal("0.01")
        )

    efectivo = efectivo.quantize(Decimal("0.01"))
    total_ventas = (efectivo + ventas_digital).quantize(Decimal("0.01"))
    total_propinas = sum(
        (datos["propinas"] for datos in agregados_metodo.values()),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    total_movimientos = sum(datos["cantidad"] for datos in agregados_metodo.values())
    monto_esperado = (sesion.monto_inicial + efectivo).quantize(Decimal("0.01"))

    desglose_metodos = []
    for codigo, etiqueta in METODOS_PAGO_ORDEN:
        datos = agregados_metodo.get(
            codigo,
            {
                "monto": (
                    efectivo
                    if (not tiene_pagos and codigo == Pago.METODO_EFECTIVO)
                    else Decimal("0.00")
                ),
                "propinas": Decimal("0.00"),
                "cantidad": 0,
            },
        )
        monto_m = datos["monto"].quantize(Decimal("0.01"))
        pct = (
            round(float((monto_m / total_ventas) * Decimal("100")), 1)
            if total_ventas > Decimal("0.00")
            else 0.0
        )
        desglose_metodos.append(
            {
                "codigo": codigo,
                "nombre": etiqueta,
                "monto": monto_m,
                "propinas": datos["propinas"].quantize(Decimal("0.01")),
                "cantidad": datos["cantidad"],
                "porcentaje": pct,
                "es_efectivo": codigo == Pago.METODO_EFECTIVO,
            }
        )

    return {
        "efectivo": efectivo,
        "ventas_digital": ventas_digital,
        "total_ventas": total_ventas,
        "total_propinas": total_propinas,
        "monto_esperado": monto_esperado,
        "total_movimientos": total_movimientos,
        "desglose_metodos": desglose_metodos,
        "movimientos": list(pagos_qs[:50]),
    }


def _enriquecer_sesion_historial(sesion, mapa_cajeros):
    """Agrega metadatos de visualización de arqueo a una sesión cerrada."""
    sesion.cajero_nombre = mapa_cajeros.get(
        sesion.cajero_id, f"Cajero #{sesion.cajero_id}"
    )
    dif = sesion.diferencia
    if dif is None or dif == Decimal("0.00"):
        sesion.arqueo_estado = "CUADRADO"
        sesion.arqueo_etiqueta = "Cuadrado exacto"
        sesion.arqueo_clase = "up"
    elif dif > Decimal("0.00"):
        sesion.arqueo_estado = "SOBRANTE"
        sesion.arqueo_etiqueta = f"Sobrante (+S/ {dif:.2f})"
        sesion.arqueo_clase = "warn"
    else:
        sesion.arqueo_estado = "FALTANTE"
        sesion.arqueo_etiqueta = f"Faltante (-S/ {abs(dif):.2f})"
        sesion.arqueo_clase = "danger"
    sesion.total_turno = (
        (sesion.monto_ventas_efectivo or Decimal("0.00"))
        + (sesion.monto_ventas_digital or Decimal("0.00"))
    ).quantize(Decimal("0.01"))
    return sesion


def _contexto_panel_caja(form_apertura=None, form_cierre=None):
    """Construye el contexto completo de la pantalla de Caja y Arqueo (PRB-60)."""
    sesion_abierta = (
        SesionCaja.objects.filter(estado=SesionCaja.ESTADO_ABIERTA)
        .order_by("-fecha_apertura", "-id")
        .first()
    )
    historial = list(
        SesionCaja.objects.filter(estado=SesionCaja.ESTADO_CERRADA).order_by(
            "-fecha_cierre", "-id"
        )[:20]
    )

    cajero_ids = [s.cajero_id for s in historial]
    if sesion_abierta:
        cajero_ids.append(sesion_abierta.cajero_id)
    mapa_cajeros = _mapa_nombres_cajeros(cajero_ids)

    resumen_actual = None
    if sesion_abierta:
        sesion_abierta.cajero_nombre = mapa_cajeros.get(
            sesion_abierta.cajero_id, f"Cajero #{sesion_abierta.cajero_id}"
        )
        resumen_actual = _calcular_resumen_sesion(sesion_abierta)
        if form_cierre is None:
            form_cierre = CierreCajaForm(
                initial={"monto_real": resumen_actual["monto_esperado"]},
                monto_esperado=resumen_actual["monto_esperado"],
            )

    if form_apertura is None:
        form_apertura = AperturaCajaForm()

    historial = [_enriquecer_sesion_historial(s, mapa_cajeros) for s in historial]

    return {
        "nav_active": "caja",
        "hoy": timezone.localdate(),
        "sesion_abierta": sesion_abierta,
        "resumen_actual": resumen_actual,
        "form_apertura": form_apertura,
        "form_cierre": form_cierre,
        "historial_sesiones": historial,
    }


@staff_required
def caja_arqueo(request):
    """Pantalla principal de apertura de turno, movimientos y Cierre Z (PRB-60)."""
    asegurar_tablas_sqlite()
    return render(request, "catalogo/caja.html", _contexto_panel_caja())


@staff_required
@require_POST
def abrir_caja(request):
    """Abre un turno de caja garantizando que solo exista una caja ABIERTA (PRB-60)."""
    asegurar_tablas_sqlite()
    form = AperturaCajaForm(request.POST)
    if not form.is_valid():
        messages.error(
            request,
            "No se pudo abrir la caja. Revisa el monto inicial ingresado.",
        )
        return render(
            request,
            "catalogo/caja.html",
            _contexto_panel_caja(form_apertura=form),
        )

    monto_inicial = form.cleaned_data["monto_inicial"]
    observaciones = form.cleaned_data["observaciones"]

    try:
        with transaction.atomic():
            ya_abierta = (
                SesionCaja.objects.select_for_update()
                .filter(estado=SesionCaja.ESTADO_ABIERTA)
                .exists()
            )
            if ya_abierta:
                messages.error(
                    request,
                    "Solo puede existir una caja ABIERTA a la vez. "
                    "Realiza el Cierre Z del turno activo antes de abrir uno nuevo.",
                )
                return redirect("catalogo:caja")

            cajero_id = _resolver_cajero_id(request.user)
            sesion = SesionCaja.objects.create(
                cajero_id=cajero_id,
                monto_inicial=monto_inicial,
                monto_ventas_efectivo=Decimal("0.00"),
                monto_ventas_digital=Decimal("0.00"),
                monto_esperado=monto_inicial,
                estado=SesionCaja.ESTADO_ABIERTA,
                observaciones=observaciones or None,
            )
    except IntegrityError:
        messages.error(
            request,
            "Solo puede existir una caja ABIERTA a la vez. "
            "Otro usuario acaba de iniciar un turno activo.",
        )
        return redirect("catalogo:caja")

    messages.success(
        request,
        f"Turno de Caja #{sesion.id} abierto correctamente con fondo inicial "
        f"de S/ {monto_inicial:.2f}.",
    )
    return redirect("catalogo:caja")


@staff_required
@require_POST
def cerrar_caja(request):
    """Ejecuta el arqueo físico y Cierre Z calculando sobrantes o faltantes (PRB-60)."""
    asegurar_tablas_sqlite()

    with transaction.atomic():
        sesion = (
            SesionCaja.objects.select_for_update()
            .filter(estado=SesionCaja.ESTADO_ABIERTA)
            .order_by("-fecha_apertura", "-id")
            .first()
        )
        if sesion is None:
            messages.error(
                request,
                "No existe ninguna sesión de caja ABIERTA para realizar el cierre.",
            )
            return redirect("catalogo:caja")

        resumen = _calcular_resumen_sesion(sesion)
        monto_esperado = resumen["monto_esperado"]
        form = CierreCajaForm(request.POST, monto_esperado=monto_esperado)

        if not form.is_valid():
            errores = []
            for lista in form.errors.values():
                errores.extend(lista)
            mensaje_error = (
                " ".join(errores)
                if errores
                else "Datos de cierre inválidos. Verifica el efectivo contado."
            )
            messages.error(request, mensaje_error)
            return render(
                request,
                "catalogo/caja.html",
                _contexto_panel_caja(form_cierre=form),
            )

        monto_real = form.cleaned_data["monto_real"]
        nota_cierre = form.cleaned_data["observaciones"]
        diferencia = (monto_real - monto_esperado).quantize(Decimal("0.01"))

        if sesion.observaciones and nota_cierre:
            observaciones_finales = f"{sesion.observaciones} | Cierre Z: {nota_cierre}"
        elif nota_cierre:
            observaciones_finales = nota_cierre
        else:
            observaciones_finales = sesion.observaciones

        sesion.monto_ventas_efectivo = resumen["efectivo"]
        sesion.monto_ventas_digital = resumen["ventas_digital"]
        sesion.monto_esperado = monto_esperado
        sesion.monto_real = monto_real
        sesion.diferencia = diferencia
        sesion.fecha_cierre = timezone.now()
        sesion.estado = SesionCaja.ESTADO_CERRADA
        sesion.observaciones = observaciones_finales
        sesion.save()

    if diferencia == Decimal("0.00"):
        messages.success(
            request,
            f"Cierre Z de Caja #{sesion.id} completado: arqueo CUADRADO "
            f"exacto (S/ {monto_real:.2f}).",
        )
    elif diferencia > Decimal("0.00"):
        messages.warning(
            request,
            f"Cierre Z de Caja #{sesion.id} registrado con SOBRANTE de +S/ {diferencia:.2f} "
            f"(Esperado: S/ {monto_esperado:.2f} · Contado: S/ {monto_real:.2f}).",
        )
    else:
        messages.warning(
            request,
            f"Cierre Z de Caja #{sesion.id} registrado con FALTANTE de -S/ {abs(diferencia):.2f} "
            f"(Esperado: S/ {monto_esperado:.2f} · Contado: S/ {monto_real:.2f}).",
        )
    return redirect("catalogo:caja")


@staff_required
def reportes_ventas(request):
    """Reporte operativo de ventas del día, ticket promedio y medios de pago (PRB-61).

    Alcance estricto PRB-61: ventas del día, ticket promedio, desglose por medio de
    pago (EFECTIVO, YAPE, PLIN, TARJETA) y conciliación con sesiones de caja.
    El ranking de platos y la exportación CSV quedan fuera de esta entrega.
    """
    asegurar_tablas_sqlite()
    hoy = timezone.localdate()
    fecha_param = (request.GET.get("fecha") or "").strip()

    fecha_consulta = hoy
    if fecha_param:
        try:
            fecha_consulta = date.fromisoformat(fecha_param)
        except ValueError:
            messages.warning(
                request,
                "Formato de fecha inválido. Mostrando el reporte operativo de hoy.",
            )
            fecha_consulta = hoy

    pagos_dia_qs = (
        Pago.objects.filter(fecha_pago__date=fecha_consulta)
        .select_related("pedido", "mesa", "sesion_caja")
        .order_by("-fecha_pago", "-id")
    )

    ventas_dia, pedidos_cobrados = _calcular_ventas_y_pedidos_fecha(fecha_consulta)
    ticket_promedio = (
        (ventas_dia / Decimal(pedidos_cobrados)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if pedidos_cobrados > 0
        else Decimal("0.00")
    )

    agregados_metodo = {
        item["metodo"]: {
            "monto": item["monto"] or Decimal("0.00"),
            "propinas": item["propinas"] or Decimal("0.00"),
            "transacciones": item["transacciones"] or 0,
            "pedidos": item["pedidos"] or 0,
        }
        for item in pagos_dia_qs.values("metodo").annotate(
            monto=Sum("monto"),
            propinas=Sum("propina"),
            transacciones=Count("id"),
            pedidos=Count("pedido_id", distinct=True),
        )
    }

    total_pagos_registrados = sum(
        (d["monto"] for d in agregados_metodo.values()),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    total_propinas = sum(
        (d["propinas"] for d in agregados_metodo.values()),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    total_transacciones = sum(d["transacciones"] for d in agregados_metodo.values())

    desglose_medios = []
    for codigo, etiqueta in METODOS_PAGO_ORDEN:
        datos = agregados_metodo.get(
            codigo,
            {
                "monto": Decimal("0.00"),
                "propinas": Decimal("0.00"),
                "transacciones": 0,
                "pedidos": 0,
            },
        )
        monto_m = datos["monto"].quantize(Decimal("0.01"))
        pct = (
            round(float((monto_m / total_pagos_registrados) * Decimal("100")), 1)
            if total_pagos_registrados > Decimal("0.00")
            else 0.0
        )
        desglose_medios.append(
            {
                "codigo": codigo,
                "nombre": etiqueta,
                "monto": monto_m,
                "propinas": datos["propinas"].quantize(Decimal("0.01")),
                "transacciones": datos["transacciones"],
                "pedidos": datos["pedidos"],
                "porcentaje": pct,
                "es_efectivo": codigo == Pago.METODO_EFECTIVO,
            }
        )

    total_efectivo = (
        agregados_metodo.get(Pago.METODO_EFECTIVO, {}).get("monto", Decimal("0.00"))
    ).quantize(Decimal("0.01"))
    total_digital = (total_pagos_registrados - total_efectivo).quantize(Decimal("0.01"))
    pct_efectivo = (
        round(float((total_efectivo / total_pagos_registrados) * Decimal("100")), 1)
        if total_pagos_registrados > Decimal("0.00")
        else 0.0
    )
    pct_digital = (
        round(100.0 - pct_efectivo, 1)
        if total_pagos_registrados > Decimal("0.00")
        else 0.0
    )

    # Conciliación con sesiones de caja abiertas o cerradas en la fecha consultada
    sesiones_dia = list(
        SesionCaja.objects.filter(
            Q(fecha_apertura__date=fecha_consulta)
            | Q(fecha_cierre__date=fecha_consulta)
        ).order_by("-fecha_apertura", "-id")
    )
    mapa_cajeros = _mapa_nombres_cajeros([s.cajero_id for s in sesiones_dia])
    for s in sesiones_dia:
        if s.estado == SesionCaja.ESTADO_ABIERTA:
            res_s = _calcular_resumen_sesion(s)
            s.cajero_nombre = mapa_cajeros.get(s.cajero_id, f"Cajero #{s.cajero_id}")
            s.monto_ventas_efectivo = res_s["efectivo"]
            s.monto_ventas_digital = res_s["ventas_digital"]
            s.monto_esperado = res_s["monto_esperado"]
            s.total_turno = res_s["total_ventas"]
            s.arqueo_etiqueta = "Turno en curso"
            s.arqueo_clase = "neutral"
        else:
            _enriquecer_sesion_historial(s, mapa_cajeros)

    total_sesiones_dia = sum(
        (s.total_turno for s in sesiones_dia), Decimal("0.00")
    ).quantize(Decimal("0.01"))

    context = {
        "nav_active": "reportes",
        "hoy": hoy,
        "fecha_consulta": fecha_consulta,
        "es_hoy": fecha_consulta == hoy,
        "ventas_dia": ventas_dia,
        "pedidos_cobrados": pedidos_cobrados,
        "ticket_promedio": ticket_promedio,
        "total_pagos_registrados": total_pagos_registrados,
        "total_propinas": total_propinas,
        "total_transacciones": total_transacciones,
        "total_efectivo": total_efectivo,
        "total_digital": total_digital,
        "pct_efectivo": pct_efectivo,
        "pct_digital": pct_digital,
        "desglose_medios": desglose_medios,
        "pagos_recientes": list(pagos_dia_qs[:50]),
        "sesiones_dia": sesiones_dia,
        "total_sesiones_dia": total_sesiones_dia,
    }
    return render(request, "catalogo/reportes.html", context)


def _sincronizar_stock_seguro():
    """Ejecuta conciliación idempotente de stock con pedidos POS si las tablas existen."""
    try:
        return sincronizar_stock_con_pedidos()
    except DatabaseError:
        return {"descuentos": 0, "reversiones": 0}


@staff_required
def stock_del_dia(request):
    """Tablero operativo de Inventario Reducido / Stock del Día (PRB-59)."""
    asegurar_tablas_sqlite()
    resultado_sync = _sincronizar_stock_seguro()

    categoria_filtro = (request.GET.get("categoria") or "").strip()
    modo_filtro = (request.GET.get("modo") or "todos").strip()
    busqueda = (request.GET.get("q") or "").strip()

    platos_qs = Producto.objects.select_related("categoria").order_by(
        "categoria__id", "nombre"
    )
    if busqueda:
        platos_qs = platos_qs.filter(
            Q(nombre__icontains=busqueda) | Q(categoria__nombre__icontains=busqueda)
        )
    categoria_activa = None
    if categoria_filtro.isdigit():
        categoria_activa = int(categoria_filtro)
        platos_qs = platos_qs.filter(categoria_id=categoria_activa)

    if modo_filtro == "con_cupo":
        platos_qs = platos_qs.filter(stock_disponible__isnull=False)
    elif modo_filtro == "bajo_stock":
        platos_qs = platos_qs.filter(
            disponible=True,
            stock_disponible__isnull=False,
            stock_disponible__gt=0,
            stock_minimo__gt=0,
            stock_disponible__lte=F("stock_minimo"),
        )
    elif modo_filtro == "agotados":
        platos_qs = platos_qs.filter(Q(disponible=False) | Q(stock_disponible=0))
    elif modo_filtro == "ilimitados":
        platos_qs = platos_qs.filter(stock_disponible__isnull=True)

    todos_qs = Producto.objects.all()
    total_platos = todos_qs.count()
    con_cupo = todos_qs.filter(stock_disponible__isnull=False).count()
    ilimitados = todos_qs.filter(stock_disponible__isnull=True).count()
    agotados = todos_qs.filter(Q(disponible=False) | Q(stock_disponible=0)).count()
    bajo_stock = todos_qs.filter(
        disponible=True,
        stock_disponible__isnull=False,
        stock_disponible__gt=0,
        stock_minimo__gt=0,
        stock_disponible__lte=F("stock_minimo"),
    ).count()
    porciones_totales = (
        todos_qs.filter(stock_disponible__gt=0).aggregate(s=Sum("stock_disponible"))[
            "s"
        ]
        or 0
    )

    try:
        movimientos_recientes = list(
            MovimientoStock.objects.select_related("producto", "pedido").order_by(
                "-fecha", "-id"
            )[:30]
        )
    except DatabaseError:
        movimientos_recientes = []

    categorias = list(
        Categoria.objects.annotate(total_platos=Count("productos")).order_by("id")
    )

    context = {
        "nav_active": "stock",
        "platos": list(platos_qs),
        "categorias": categorias,
        "categoria_activa": categoria_activa,
        "modo_filtro": modo_filtro,
        "busqueda": busqueda,
        "resultado_sync": resultado_sync,
        "kpis_stock": {
            "total_platos": total_platos,
            "con_cupo": con_cupo,
            "ilimitados": ilimitados,
            "bajo_stock": bajo_stock,
            "agotados": agotados,
            "porciones_totales": porciones_totales,
        },
        "movimientos_recientes": movimientos_recientes,
    }
    return render(request, "catalogo/stock_dia.html", context)


@staff_required
@require_POST
def fijar_stock_plato(request, pk):
    """Fija el cupo diario de porciones o pasa un plato a stock ilimitado (PRB-59)."""
    asegurar_tablas_sqlite()
    plato = get_object_or_404(Producto, pk=pk)

    modo_ilimitado = request.POST.get("ilimitado") in ("1", "true", "on")
    stock_raw = (request.POST.get("stock_disponible") or "").strip()
    minimo_raw = (request.POST.get("stock_minimo") or "").strip()
    motivo = (request.POST.get("motivo") or "").strip()

    if modo_ilimitado or stock_raw == "":
        nuevo_stock = None
    else:
        try:
            nuevo_stock = int(stock_raw)
        except ValueError:
            msg = "El stock diario debe ser un número entero mayor o igual a 0."
            if _es_peticion_json(request):
                return JsonResponse({"ok": False, "error": msg}, status=400)
            messages.error(request, msg)
            return redirect(_url_retorno_segura(request, "catalogo:stock_dia"))

    nuevo_minimo = None
    if minimo_raw != "":
        try:
            nuevo_minimo = int(minimo_raw)
        except ValueError:
            msg = (
                "El stock mínimo de alerta debe ser un número entero mayor o igual a 0."
            )
            if _es_peticion_json(request):
                return JsonResponse({"ok": False, "error": msg}, status=400)
            messages.error(request, msg)
            return redirect(_url_retorno_segura(request, "catalogo:stock_dia"))

    try:
        plato_act, _ = fijar_stock_diario(
            producto_id=plato.id,
            stock_disponible=nuevo_stock,
            stock_minimo=nuevo_minimo,
            motivo=motivo,
            registrado_por=request.user.username,
        )
    except ValidationError as exc:
        msg = "; ".join(exc.messages)
        if _es_peticion_json(request):
            return JsonResponse({"ok": False, "error": msg}, status=400)
        messages.error(request, msg)
        return redirect(_url_retorno_segura(request, "catalogo:stock_dia"))

    if _es_peticion_json(request):
        return JsonResponse(
            {
                "ok": True,
                "id": plato_act.id,
                "nombre": plato_act.nombre,
                "stock_disponible": plato_act.stock_disponible,
                "stock_minimo": plato_act.stock_minimo,
                "disponible": plato_act.disponible,
                "stock_bajo": plato_act.stock_bajo,
            }
        )

    if plato_act.stock_disponible is None:
        messages.success(
            request,
            f"«{plato_act.nombre}» configurado en modo stock libre (ilimitado).",
        )
    elif plato_act.stock_disponible == 0:
        messages.warning(
            request,
            f"«{plato_act.nombre}» quedó en 0 porciones y se marcó como AGOTADO.",
        )
    else:
        messages.success(
            request,
            f"Stock del día de «{plato_act.nombre}» fijado en "
            f"{plato_act.stock_disponible} porción(es).",
        )
    return redirect(_url_retorno_segura(request, "catalogo:stock_dia"))


@staff_required
@require_POST
def ajustar_stock_plato(request, pk):
    """Ajusta relativamente (+/- porciones) el stock diario de un plato (PRB-59)."""
    asegurar_tablas_sqlite()
    plato = get_object_or_404(Producto, pk=pk)
    delta_raw = (request.POST.get("delta") or "").strip()
    motivo = (request.POST.get("motivo") or "").strip()

    try:
        delta = int(delta_raw)
    except ValueError:
        msg = "Indica una cantidad entera válida para ajustar el stock."
        if _es_peticion_json(request):
            return JsonResponse({"ok": False, "error": msg}, status=400)
        messages.error(request, msg)
        return redirect(_url_retorno_segura(request, "catalogo:stock_dia"))

    try:
        plato_act, _ = ajustar_stock_producto(
            producto_id=plato.id,
            delta=delta,
            motivo=motivo,
            registrado_por=request.user.username,
        )
    except ValidationError as exc:
        msg = "; ".join(exc.messages)
        if _es_peticion_json(request):
            return JsonResponse({"ok": False, "error": msg}, status=400)
        messages.error(request, msg)
        return redirect(_url_retorno_segura(request, "catalogo:stock_dia"))

    if _es_peticion_json(request):
        return JsonResponse(
            {
                "ok": True,
                "id": plato_act.id,
                "stock_disponible": plato_act.stock_disponible,
                "disponible": plato_act.disponible,
                "stock_bajo": plato_act.stock_bajo,
            }
        )

    signo = f"+{delta}" if delta > 0 else str(delta)
    messages.success(
        request,
        f"Ajuste aplicado ({signo}) en «{plato_act.nombre}»: "
        f"{plato_act.stock_disponible} porción(es) disponibles.",
    )
    return redirect(_url_retorno_segura(request, "catalogo:stock_dia"))


@staff_required
@require_POST
def carga_masiva_stock(request):
    """Aplica cupo diario inicial por categoría o sobre toda la carta (PRB-59)."""
    asegurar_tablas_sqlite()
    accion = (request.POST.get("accion") or "fijar_cupo").strip()
    categoria_id = (request.POST.get("categoria_id") or "").strip()
    cupo_raw = (request.POST.get("cupo") or "").strip()
    minimo_raw = (request.POST.get("stock_minimo") or "").strip()

    qs = Producto.objects.all().order_by("id")
    nombre_alcance = "toda la carta"
    if categoria_id.isdigit():
        cat = get_object_or_404(Categoria, pk=int(categoria_id))
        qs = qs.filter(categoria=cat)
        nombre_alcance = f"la categoría «{cat.nombre}»"

    platos_ids = list(qs.values_list("id", flat=True))
    if not platos_ids:
        messages.warning(request, "No hay platos en el alcance seleccionado.")
        return redirect("catalogo:stock_dia")

    if accion == "modo_libre":
        with transaction.atomic():
            for pid in platos_ids:
                fijar_stock_diario(
                    producto_id=pid,
                    stock_disponible=None,
                    motivo=f"Paso masivo a stock libre en {nombre_alcance}",
                    registrado_por=request.user.username,
                )
        messages.success(
            request,
            f"{len(platos_ids)} plato(s) de {nombre_alcance} configurados en stock libre.",
        )
        return redirect("catalogo:stock_dia")

    try:
        cupo = int(cupo_raw)
        if cupo < 0:
            raise ValueError
    except ValueError:
        messages.error(
            request, "Ingresa un cupo entero mayor o igual a 0 para la carga masiva."
        )
        return redirect("catalogo:stock_dia")

    nuevo_minimo = None
    if minimo_raw != "":
        try:
            nuevo_minimo = int(minimo_raw)
            if nuevo_minimo < 0:
                raise ValueError
        except ValueError:
            messages.error(
                request, "El umbral mínimo debe ser un entero mayor o igual a 0."
            )
            return redirect("catalogo:stock_dia")

    with transaction.atomic():
        for pid in platos_ids:
            fijar_stock_diario(
                producto_id=pid,
                stock_disponible=cupo,
                stock_minimo=nuevo_minimo,
                motivo=f"Carga masiva del turno en {nombre_alcance}",
                registrado_por=request.user.username,
            )

    messages.success(
        request,
        f"Carga diaria completada: {len(platos_ids)} plato(s) de {nombre_alcance} "
        f"fijados en {cupo} porción(es).",
    )
    return redirect("catalogo:stock_dia")


def _asegurar_roles_canonicos():
    """Garantiza que existan los 4 roles oficiales para el formulario de personal."""
    asegurar_tablas_sqlite()
    if Rol.objects.count() < len(ROLES_OFICIALES):
        for nombre_rol in ROLES_OFICIALES:
            Rol.objects.get_or_create(nombre=nombre_rol)


@staff_required
def personal_operativo(request):
    """Gestión de usuarios operativos POS, roles, PIN BCrypt y auditoría PRB-52 / PRB-84."""
    _asegurar_roles_canonicos()
    usuarios = Usuario.objects.select_related("rol").order_by("rol_id", "username")
    roles = Rol.objects.order_by("id")
    auditoria = auditar_datos_produccion()

    try:
        turnos = list(Turno.objects.order_by("hora_inicio", "id"))
        terminales = list(Terminal.objects.order_by("codigo"))
        sesiones_mozo = list(
            SesionMozo.objects.select_related("usuario", "terminal", "turno").order_by(
                "-inicio", "-id"
            )[:20]
        )
    except DatabaseError:
        turnos = []
        terminales = []
        sesiones_mozo = []

    context = {
        "nav_active": "personal",
        "usuarios": usuarios,
        "roles": roles,
        "form_usuario": UsuarioOperativoForm(),
        "auditoria": auditoria,
        "total_usuarios": usuarios.count(),
        "total_con_pin": sum(1 for u in usuarios if u.tiene_pin),
        "total_bloqueados": sum(1 for u in usuarios if u.esta_bloqueado),
        "turnos": turnos,
        "terminales": terminales,
        "sesiones_mozo": sesiones_mozo,
    }
    return render(request, "catalogo/personal.html", context)


@staff_required
@require_POST
def crear_usuario_operativo(request):
    """Alta de cuenta operativa POS con clave_hash y pin_hash en BCrypt cost 10."""
    _asegurar_roles_canonicos()
    form = UsuarioOperativoForm(request.POST)
    if not form.is_valid():
        for _, errs in form.errors.items():
            for err in errs:
                messages.error(request, err)
        return redirect("catalogo:personal")

    nuevo = Usuario(
        username=form.cleaned_data["username"],
        rol=form.cleaned_data["rol"],
        intentos_fallidos=0,
        bloqueado_hasta=None,
    )
    nuevo.set_password_bcrypt(form.cleaned_data["password"])
    nuevo.set_pin_bcrypt(form.cleaned_data["pin"])
    nuevo.save()
    messages.success(
        request,
        f"Usuario operativo '{nuevo.username}' ({nuevo.rol.nombre}) registrado "
        "con contraseña y PIN BCrypt cost 10.",
    )
    return redirect("catalogo:personal")


@staff_required
@require_POST
def actualizar_credenciales_operativas(request, pk):
    """Actualiza rol, contraseña BCrypt y/o PIN de 4 dígitos de un usuario POS."""
    _asegurar_roles_canonicos()
    usuario = get_object_or_404(Usuario, pk=pk)

    rol_id = (request.POST.get("rol_id") or "").strip()
    nueva_clave = request.POST.get("nueva_clave") or ""
    nuevo_pin = (request.POST.get("nuevo_pin") or "").strip()

    campos = []
    try:
        if rol_id.isdigit():
            nuevo_rol = get_object_or_404(Rol, pk=int(rol_id))
            if usuario.rol_id != nuevo_rol.id:
                usuario.rol = nuevo_rol
                campos.append("rol")
        if nueva_clave.strip():
            usuario.set_password_bcrypt(nueva_clave)
            campos.append("clave_hash")
        if nuevo_pin:
            usuario.set_pin_bcrypt(nuevo_pin)
            campos.append("pin_hash")
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect("catalogo:personal")

    if not campos:
        messages.info(request, f"Sin cambios pendientes para '{usuario.username}'.")
        return redirect("catalogo:personal")

    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    campos.extend(["intentos_fallidos", "bloqueado_hasta"])
    usuario.save(update_fields=campos)
    messages.success(
        request,
        f"Credenciales BCrypt actualizadas para '{usuario.username}'.",
    )
    return redirect("catalogo:personal")


@staff_required
@require_POST
def desbloquear_usuario_operativo(request, pk):
    """Restablece intentos fallidos y desbloquea temporalmente una cuenta POS."""
    asegurar_tablas_sqlite()
    usuario = get_object_or_404(Usuario, pk=pk)
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
    messages.success(request, f"Cuenta operativa '{usuario.username}' desbloqueada.")
    return redirect("catalogo:personal")


@staff_required
@require_POST
def sincronizar_seeds_produccion_view(request):
    """Ejecuta de forma idempotente la migración de datos reales PRB-52."""
    res = cargar_datos_produccion()
    messages.success(
        request,
        f"Datos reales sincronizados (PRB-52): usuarios +{res['usuarios_creados']}/"
        f"~{res['usuarios_actualizados']}, platos +{res['platos_creados']}/"
        f"~{res['platos_actualizados']}, mesas +{res['mesas_creadas']}/"
        f"~{res['mesas_actualizadas']}.",
    )
    return redirect("catalogo:personal")


# =============================================================================
# KDS DE COCINA: ESTACIONES, SEMÁFORO SLA Y TIEMPO REAL (PRB-57 · P-10)
# =============================================================================


def resolver_usuario_operativo_id(user):
    """Resuelve un usuario_id válido de la tabla 'usuario' para el usuario autenticado (auth_user).

    Garantiza compatibilidad con las foreign keys en PostgreSQL evitando ForeignKeyViolation.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None

    if isinstance(user, Usuario) and getattr(user, "id", None):
        if Usuario.objects.filter(pk=user.id).exists():
            return user.id

    username = getattr(user, "username", None)
    if username:
        operativo = Usuario.objects.filter(username__iexact=username).first()
        if operativo:
            return operativo.id

    cocinero_o_admin = (
        Usuario.objects.filter(rol__nombre__in=["COCINERO", "ADMIN", "CAJERO"])
        .order_by("id")
        .first()
    )
    if cocinero_o_admin:
        return cocinero_o_admin.id

    primer_usuario = Usuario.objects.order_by("id").first()
    if primer_usuario:
        return primer_usuario.id

    return None


@staff_required
def kds_cocina(request):
    """Pantalla KDS de cocina en tiempo real con estaciones y semáforo SLA."""
    asegurar_tablas_sqlite()

    estacion = (request.GET.get("estacion") or "").strip().upper()
    estado = (request.GET.get("estado") or "activos").strip().lower()

    comandas = obtener_comandas_kds(estacion=estacion, estado_filtro=estado)
    kpis = resumen_kpis_kds()

    context = {
        "nav_active": "cocina",
        "comandas": comandas,
        "kpis": kpis,
        "estaciones_info": ESTACIONES_INFO,
        "estacion_activa": estacion,
        "estado_activo": estado,
        "ahora": timezone.now(),
    }
    return render(request, "catalogo/kds.html", context)


@staff_required
@require_POST
def kds_avanzar_pedido(request, pk):
    """Avanza de forma transaccional el estado de preparación de una comanda o estación."""
    asegurar_tablas_sqlite()
    nuevo_estado = (request.POST.get("nuevo_estado") or "").strip().upper()
    motivo = (request.POST.get("motivo") or "").strip()
    estacion = (request.POST.get("estacion") or "").strip().upper()
    usuario_id = resolver_usuario_operativo_id(request.user)

    try:
        pedido = avanzar_estado_comanda(
            pedido_id=pk,
            nuevo_estado=nuevo_estado,
            estacion=estacion if estacion else None,
            usuario_id=usuario_id,
            motivo=motivo,
        )
    except (Pedido.DoesNotExist, ValidationError) as exc:
        msg = str(exc)
        if request.headers.get(
            "x-requested-with"
        ) == "XMLHttpRequest" or "application/json" in request.META.get(
            "HTTP_ACCEPT", ""
        ):
            return JsonResponse({"ok": False, "error": msg}, status=400)
        messages.error(request, msg)
        return redirect("catalogo:kds_cocina")

    if request.headers.get(
        "x-requested-with"
    ) == "XMLHttpRequest" or "application/json" in request.META.get("HTTP_ACCEPT", ""):
        return JsonResponse(
            {
                "ok": True,
                "pedido_id": pedido.id,
                "nuevo_estado": pedido.estado,
                "estado_display": pedido.get_estado_display(),
            }
        )

    messages.success(
        request,
        f"Comanda #{pedido.id} ({pedido.origen_display}) "
        f"actualizada a {pedido.get_estado_display()}.",
    )
    redirect_url = reverse("catalogo:kds_cocina")
    query_parts = []
    if request.POST.get("estacion"):
        query_parts.append(f"estacion={request.POST.get('estacion')}")
    if request.POST.get("estado"):
        query_parts.append(f"estado={request.POST.get('estado')}")
    if query_parts:
        redirect_url = f"{redirect_url}?{'&'.join(query_parts)}"
    return redirect(redirect_url)


@staff_required
@require_POST
def kds_avanzar_item(request, detalle_id):
    """Avanza atómicamente el estado individual de un plato en el KDS (PRB-57, PRB-86)."""
    asegurar_tablas_sqlite()
    nuevo_estado = (request.POST.get("nuevo_estado") or "").strip().upper()
    motivo = (request.POST.get("motivo") or "").strip()
    usuario_id = resolver_usuario_operativo_id(request.user)

    try:
        detalle = avanzar_estado_item(
            detalle_id=detalle_id,
            nuevo_estado=nuevo_estado,
            usuario_id=usuario_id,
            motivo=motivo,
        )
    except (DetallePedido.DoesNotExist, ValidationError) as exc:
        msg = str(exc)
        if request.headers.get(
            "x-requested-with"
        ) == "XMLHttpRequest" or "application/json" in request.META.get(
            "HTTP_ACCEPT", ""
        ):
            return JsonResponse({"ok": False, "error": msg}, status=400)
        messages.error(request, msg)
        return redirect("catalogo:kds_cocina")

    if request.headers.get(
        "x-requested-with"
    ) == "XMLHttpRequest" or "application/json" in request.META.get("HTTP_ACCEPT", ""):
        return JsonResponse(
            {
                "ok": True,
                "detalle_id": detalle.id,
                "pedido_id": detalle.pedido_id,
                "nuevo_estado_item": detalle.estado_item,
                "estado_item_display": detalle.get_estado_item_display(),
                "pedido_estado": detalle.pedido.estado,
                "pedido_estado_display": detalle.pedido.get_estado_display(),
            }
        )

    messages.success(
        request,
        f"{detalle.producto.nombre} actualizado a {detalle.get_estado_item_display()}.",
    )
    redirect_url = reverse("catalogo:kds_cocina")
    query_parts = []
    if request.POST.get("estacion"):
        query_parts.append(f"estacion={request.POST.get('estacion')}")
    if request.POST.get("estado"):
        query_parts.append(f"estado={request.POST.get('estado')}")
    if query_parts:
        redirect_url = f"{redirect_url}?{'&'.join(query_parts)}"
    return redirect(redirect_url)


@staff_required
def kds_api_comandas(request):
    """Endpoint JSON liviano para refresco automático (polling) del KDS en vivo."""
    asegurar_tablas_sqlite()
    estacion = (request.GET.get("estacion") or "").strip().upper()
    estado = (request.GET.get("estado") or "activos").strip().lower()

    comandas = obtener_comandas_kds(estacion=estacion, estado_filtro=estado)
    kpis = resumen_kpis_kds()
    payload = serializar_comandas_json(comandas)

    return JsonResponse(
        {
            "ok": True,
            "kpis": kpis,
            "total_comandas": len(payload),
            "comandas": payload,
            "timestamp": timezone.now().isoformat(),
        }
    )


# =============================================================================
# COLA DE IMPRESIÓN TÉRMICA ESC/POS 80 MM (PRB-58 / P-11)
# =============================================================================


@staff_required
def impresion_monitor(request):
    """Monitor operativo de la cola de impresión térmica ESC/POS de 80 mm (PRB-58)."""
    asegurar_tablas_sqlite()
    estado_filtro = (request.GET.get("estado") or "todos").strip().lower()
    tipo_filtro = (request.GET.get("tipo") or "todos").strip().upper()

    qs = ImpresionCola.objects.select_related("pedido").order_by(
        "-fecha_creacion", "-id"
    )

    if estado_filtro == "pendientes":
        qs = qs.filter(estado=ImpresionCola.ESTADO_PENDIENTE)
    elif estado_filtro == "impresos":
        qs = qs.filter(estado=ImpresionCola.ESTADO_IMPRESO)
    elif estado_filtro == "fallidos":
        qs = qs.filter(estado=ImpresionCola.ESTADO_FALLIDO)

    if tipo_filtro in [ImpresionCola.TIPO_COMANDA, ImpresionCola.TIPO_PRECUENTA]:
        qs = qs.filter(tipo=tipo_filtro)

    hoy = timezone.localdate()
    total_pendientes = ImpresionCola.objects.filter(
        estado=ImpresionCola.ESTADO_PENDIENTE
    ).count()
    total_impresos_hoy = ImpresionCola.objects.filter(
        estado=ImpresionCola.ESTADO_IMPRESO, fecha_impresion__date=hoy
    ).count()
    total_fallidos = ImpresionCola.objects.filter(
        estado=ImpresionCola.ESTADO_FALLIDO
    ).count()

    trabajos = list(qs[:50])

    context = {
        "nav_active": "impresion",
        "trabajos": trabajos,
        "estado_filtro": estado_filtro,
        "tipo_filtro": tipo_filtro,
        "total_pendientes": total_pendientes,
        "total_impresos_hoy": total_impresos_hoy,
        "total_fallidos": total_fallidos,
        "total_mostrados": len(trabajos),
        "printer_host": PRINTER_HOST_DEFAULT,
        "printer_port": PRINTER_PORT_DEFAULT,
        "printer_mode": PRINTER_MODE_DEFAULT,
    }
    return render(request, "catalogo/impresion.html", context)


@staff_required
def impresion_reintentar(request, pk):
    """Reintenta un trabajo de impresión en cola (PRB-58)."""
    asegurar_tablas_sqlite()
    exito, mensaje = reintentar_trabajo(pk)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": exito, "mensaje": mensaje, "id": pk})

    if exito:
        messages.success(request, f"Trabajo #{pk} reintentado exitosamente.")
    else:
        messages.error(request, f"Error al reintentar trabajo #{pk}: {mensaje}")

    return redirect("catalogo:impresion_monitor")


@staff_required
def impresion_despachar_pendientes(request):
    """Despacha todos los trabajos pendientes de la cola (PRB-58)."""
    asegurar_tablas_sqlite()
    if request.method == "POST":
        resultados = despachar_cola_pendientes(limite=20)
        exitosos = sum(1 for r in resultados if r["exito"])
        total = len(resultados)

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": True, "total": total, "exitosos": exitosos})

        messages.info(
            request,
            f"Se procesaron {total} trabajos ({exitosos} impresos correctamente).",
        )
    return redirect("catalogo:impresion_monitor")


@staff_required
def impresion_imprimir_pedido(request, pedido_id):
    """Encola y despacha comanda o pre-cuenta para un pedido específico (PRB-58)."""
    asegurar_tablas_sqlite()
    pedido = get_object_or_404(Pedido, id=pedido_id)
    tipo = (
        request.POST.get("tipo")
        or request.GET.get("tipo")
        or ImpresionCola.TIPO_COMANDA
    ).upper()
    estacion = request.POST.get("estacion") or request.GET.get("estacion") or None

    trabajo = reimprimir_pedido(pedido.id, tipo=tipo, estacion=estacion)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        if trabajo:
            return JsonResponse(
                {
                    "ok": True,
                    "trabajo_id": trabajo.id,
                    "estado": trabajo.estado,
                    "tipo": trabajo.tipo,
                    "mensaje": (
                        f"{trabajo.get_tipo_display()} #{trabajo.id} "
                        f"encolada ({trabajo.estado})."
                    ),
                }
            )
        return JsonResponse(
            {"ok": False, "mensaje": "No se pudo generar el trabajo de impresión."},
            status=400,
        )

    if trabajo and trabajo.estado == ImpresionCola.ESTADO_IMPRESO:
        messages.success(
            request,
            f"{trabajo.get_tipo_display()} para Pedido #{pedido.id} "
            f"impresa correctamente en 80 mm.",
        )
    elif trabajo:
        messages.warning(
            request,
            f"{trabajo.get_tipo_display()} encolada con estado "
            f"{trabajo.get_estado_display()}: {trabajo.error or ''}",
        )
    else:
        messages.error(
            request, f"No se pudo encolar la impresión para el Pedido #{pedido.id}."
        )

    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
        or reverse("catalogo:impresion_monitor")
    )
    return redirect(next_url)


@staff_required
def impresion_api_cola(request):
    """Endpoint JSON liviano para monitoreo en vivo de la cola de impresión térmica."""
    asegurar_tablas_sqlite()
    qs = ImpresionCola.objects.order_by("-fecha_creacion")[:20]

    trabajos_data = []
    for t in qs:
        trabajos_data.append(
            {
                "id": t.id,
                "pedido_id": t.pedido_id,
                "tipo": t.tipo,
                "estacion": t.estacion,
                "estado": t.estado,
                "intentos": t.intentos,
                "error": t.error,
                "fecha_creacion": formatear_fecha(t.fecha_creacion),
                "fecha_impresion": (
                    formatear_fecha(t.fecha_impresion) if t.fecha_impresion else None
                ),
            }
        )

    pendientes = ImpresionCola.objects.filter(
        estado=ImpresionCola.ESTADO_PENDIENTE
    ).count()
    fallidos = ImpresionCola.objects.filter(estado=ImpresionCola.ESTADO_FALLIDO).count()

    return JsonResponse(
        {
            "ok": True,
            "total_pendientes": pendientes,
            "total_fallidos": fallidos,
            "trabajos": trabajos_data,
            "timestamp": timezone.now().isoformat(),
        }
    )
