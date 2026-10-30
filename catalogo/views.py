"""Vistas del módulo web para gestión de catálogo, precios y pesca del día (PRB-19)."""

from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError
from django.db.models import Avg, Count, Max, Min, ProtectedError, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import CategoriaForm, ProductoForm
from .models import Categoria, Producto
from .sqlite_bootstrap import asegurar_tablas_sqlite, poblar_carta_ejemplo


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
            "precio_promedio": float(
                round(cat.precio_promedio or Decimal("0.00"), 2)
            ),
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
        productos_qs.order_by("disponible", "categoria__id", "nombre")[:8]
    )

    context = {
        "nav_active": "dashboard",
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
        plato.disponible = True
    elif valor_explicito in ("false", "0", "off"):
        plato.disponible = False
    else:
        plato.disponible = not plato.disponible
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
        nuevo_precio = Decimal(precio_raw).quantize(Decimal("0.01"))
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
        messages.warning(request, "Selecciona al menos un plato para aplicar el cambio.")
        return redirect(_url_retorno_segura(request, "catalogo:platos_list"))

    qs = Producto.objects.filter(pk__in=ids)
    if accion == "marcar_disponible":
        actualizados = qs.update(disponible=True)
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
    actualizados = categoria.productos.update(disponible=estado)
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
    cat_nuevas, platos_nuevos = poblar_carta_ejemplo()
    if cat_nuevas or platos_nuevos:
        messages.success(
            request,
            f"Se agregaron {cat_nuevas} categoría(s) y {platos_nuevos} plato(s) marinos.",
        )
    else:
        messages.info(request, "Todos los platos de ejemplo ya estaban en la carta.")
    return redirect(_url_retorno_segura(request, "catalogo:dashboard"))
