from decimal import Decimal
import re

import bcrypt
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Categoria(models.Model):
    """Categoría de platos o productos.

    Regla D7 (docs/db/DDL-OWNERSHIP.md): la tabla 'categoria' es creada y
    gestionada exclusivamente por db/schema.sql en PostgreSQL. Django no
    administra su DDL (managed = False).
    """

    nombre = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Nombre",
    )

    class Meta:
        db_table = "categoria"
        managed = False
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ["id"]

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    """Plato o producto ofrecido en el restaurante.

    Regla D7 (docs/db/DDL-OWNERSHIP.md): la tabla 'producto' es creada y
    gestionada exclusivamente por db/schema.sql en PostgreSQL (managed = False).
    Soporta alta de platos marinos, actualización de precios y control del stock
    diario según pesca del día (PE-19).
    """

    ESTACION_BARRA_FRIA = "BARRA_FRIA"
    ESTACION_COCINA_CALIENTE = "COCINA_CALIENTE"
    ESTACION_BEBIDAS = "BEBIDAS"
    ESTACION_POSTRES = "POSTRES"

    ESTACIONES_CHOICES = [
        (ESTACION_BARRA_FRIA, "Barra Fría (Cevichería)"),
        (ESTACION_COCINA_CALIENTE, "Cocina Caliente"),
        (ESTACION_BEBIDAS, "Bebidas"),
        (ESTACION_POSTRES, "Postres"),
    ]

    nombre = models.CharField(
        max_length=150,
        verbose_name="Nombre del plato",
    )
    descripcion = models.TextField(
        blank=True,
        null=True,
        verbose_name="Descripción",
    )
    precio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Precio (S/)",
        help_text="Precio en soles peruanos. Debe ser mayor a 0.",
    )
    disponible = models.BooleanField(
        default=True,
        verbose_name="Disponible (pesca del día)",
        help_text="Indica si el plato cuenta con stock disponible según la pesca del día.",
    )
    stock_disponible = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="Stock disponible del día",
        help_text=(
            "Cupo de porciones del día. Déjalo vacío para stock libre/ilimitado."
        ),
    )
    stock_minimo = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Alerta de stock mínimo",
        help_text="Umbral opcional para mostrar alerta visual de pocas porciones.",
    )
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.RESTRICT,
        db_column="categoria_id",
        related_name="productos",
        verbose_name="Categoría",
    )
    imagen_url = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="URL de imagen",
        help_text="Ruta o URL de la imagen del plato (opcional).",
    )

    class Meta:
        db_table = "producto"
        managed = False
        verbose_name = "Producto / Plato"
        verbose_name_plural = "Productos / Platos"
        ordering = ["categoria", "nombre"]

    @property
    def controla_stock(self):
        """Indica si el plato tiene control numérico de cupo diario."""
        return self.stock_disponible is not None

    @property
    def estacion(self):
        """Determina la estación operativa de cocina alineada con Spring Boot."""
        if not self.categoria or not self.categoria.nombre:
            return self.ESTACION_COCINA_CALIENTE
        cat = self.categoria.nombre.upper()
        if "BEBIDA" in cat:
            return self.ESTACION_BEBIDAS
        elif "POSTRE" in cat:
            return self.ESTACION_POSTRES
        nom = (self.nombre or "").upper()
        if (
            "ENTRADA" in cat
            or "CEVICHE" in nom
            or "TIRADITO" in nom
            or "LECHE DE TIGRE" in nom
        ):
            return self.ESTACION_BARRA_FRIA
        return self.ESTACION_COCINA_CALIENTE

    @property
    def estacion_display(self):
        """Nombre legible de la estación operativa."""
        return dict(self.ESTACIONES_CHOICES).get(self.estacion, "Cocina Caliente")

    @property
    def stock_bajo(self):
        """Indica si el cupo actual está en umbral de alerta (>0 y <= stock_minimo)."""
        return (
            self.disponible
            and self.stock_disponible is not None
            and self.stock_disponible > 0
            and (self.stock_minimo or 0) > 0
            and self.stock_disponible <= self.stock_minimo
        )

    def __str__(self):
        return f"{self.nombre} (S/ {self.precio})"


class Mesa(models.Model):
    """Mesa del salón en primer o segundo piso.

    Regla D7 (docs/db/DDL-OWNERSHIP.md): la tabla 'mesa' es creada y
    gestionada exclusivamente por db/schema.sql en PostgreSQL (managed = False).
    """

    ESTADO_LIBRE = "LIBRE"
    ESTADO_ATENDIENDO = "ATENDIENDO"
    ESTADO_ATENDIDA = "ATENDIDA"
    ESTADO_OCUPADA = "OCUPADA"
    ESTADO_PIDE_CUENTA = "PIDE_CUENTA"
    ESTADO_CUENTA_SOLICITADA = "CUENTA_SOLICITADA"

    ESTADOS_CHOICES = [
        (ESTADO_LIBRE, "Libre"),
        (ESTADO_ATENDIENDO, "Atendiendo"),
        (ESTADO_ATENDIDA, "Atendida"),
        (ESTADO_OCUPADA, "Ocupada"),
        (ESTADO_PIDE_CUENTA, "Pide Cuenta"),
        (ESTADO_CUENTA_SOLICITADA, "Cuenta Solicitada"),
    ]

    numero = models.IntegerField(unique=True, verbose_name="Número de Mesa")
    capacidad = models.IntegerField(verbose_name="Capacidad")
    ubicacion = models.CharField(max_length=50, verbose_name="Ubicación")
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS_CHOICES,
        default=ESTADO_LIBRE,
        verbose_name="Estado de la mesa",
    )
    mozo_id = models.IntegerField(null=True, blank=True, verbose_name="ID Mozo")
    fecha_apertura = models.DateTimeField(
        null=True, blank=True, verbose_name="Fecha Apertura"
    )
    fecha_cierre = models.DateTimeField(
        null=True, blank=True, verbose_name="Fecha Cierre"
    )

    class Meta:
        db_table = "mesa"
        managed = False
        verbose_name = "Mesa"
        verbose_name_plural = "Mesas"
        ordering = ["numero"]

    def __str__(self):
        return f"Mesa {self.numero} ({self.ubicacion}) - {self.get_estado_display()}"


class Pedido(models.Model):
    """Comanda o pedido realizado por una mesa.

    Regla D7 (docs/db/DDL-OWNERSHIP.md): la tabla 'pedido' es creada y
    gestionada exclusivamente por db/schema.sql en PostgreSQL (managed = False).
    Utilizado para el Dashboard operativo del día (PRB-45).
    """

    ESTADO_PENDIENTE = "PENDIENTE"
    ESTADO_COCINANDO = "COCINANDO"
    ESTADO_LISTO = "LISTO"
    ESTADO_SERVIDO = "SERVIDO"
    ESTADO_COBRADO = "COBRADO"
    ESTADO_ANULADO = "ANULADO"
    ESTADO_CANCELADO = "CANCELADO"

    ESTADOS_CHOICES = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_COCINANDO, "Cocinando"),
        (ESTADO_LISTO, "Listo"),
        (ESTADO_SERVIDO, "Servido"),
        (ESTADO_COBRADO, "Cobrado"),
        (ESTADO_ANULADO, "Anulado"),
        (ESTADO_CANCELADO, "Cancelado"),
    ]

    mesa = models.ForeignKey(
        Mesa,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        db_column="mesa_id",
        related_name="pedidos",
        verbose_name="Mesa",
    )
    mozo_id = models.IntegerField(db_column="mozo_id", verbose_name="ID de Mozo")
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Creación",
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS_CHOICES,
        default=ESTADO_PENDIENTE,
        verbose_name="Estado del Pedido",
    )
    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total (S/)",
    )
    client_request_id = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        verbose_name="UUID Idempotencia",
    )
    version = models.IntegerField(
        default=1,
        verbose_name="Versión Concurrente",
    )

    SLA_MINUTOS_VERDE = 10
    SLA_MINUTOS_AMBAR = 20

    SLA_NORMAL = "NORMAL"
    SLA_ALERTA = "ALERTA"
    SLA_CRITICO = "CRITICO"

    class Meta:
        db_table = "pedido"
        managed = False
        verbose_name = "Pedido / Comanda"
        verbose_name_plural = "Pedidos / Comandas"
        ordering = ["-fecha_creacion"]

    @property
    def tiempo_transcurrido_minutos(self):
        """Minutos transcurridos desde que se emitió la comanda."""
        if not self.fecha_creacion:
            return 0
        ahora = timezone.now()
        dt = self.fecha_creacion
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        segundos = max(0, int((ahora - dt).total_seconds()))
        return segundos // 60

    @property
    def tiempo_transcurrido_formateado(self):
        """Tiempo de espera en formato legible mm:ss."""
        if not self.fecha_creacion:
            return "00:00"
        ahora = timezone.now()
        dt = self.fecha_creacion
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        segundos = max(0, int((ahora - dt).total_seconds()))
        minutos = segundos // 60
        segs = segundos % 60
        return f"{minutos:02d}:{segs:02d}"

    @property
    def nivel_sla(self):
        """Semáforo SLA del KDS de cocina: NORMAL (<10m), ALERTA (10..20m), CRITICO (>20m)."""
        mins = self.tiempo_transcurrido_minutos
        if mins < self.SLA_MINUTOS_VERDE:
            return self.SLA_NORMAL
        elif mins <= self.SLA_MINUTOS_AMBAR:
            return self.SLA_ALERTA
        return self.SLA_CRITICO

    @property
    def origen_display(self):
        """Etiqueta de origen de la comanda (Mesa X o Para llevar)."""
        if self.mesa:
            return f"Mesa {self.mesa.numero}"
        return "Para llevar"

    def __str__(self):
        return f"Pedido #{self.id} ({self.origen_display}) - S/ {self.total}"


class SesionCaja(models.Model):
    """Sesión de caja y arqueo por turno (PRB-60).

    Regla D7 (docs/db/DDL-OWNERSHIP.md): la tabla 'sesion_caja' es creada y
    gestionada exclusivamente por db/schema.sql en PostgreSQL (managed = False).
    """

    ESTADO_ABIERTA = "ABIERTA"
    ESTADO_CERRADA = "CERRADA"

    ESTADOS_CHOICES = [
        (ESTADO_ABIERTA, "Abierta"),
        (ESTADO_CERRADA, "Cerrada"),
    ]

    cajero_id = models.IntegerField(db_column="cajero_id", verbose_name="ID Cajero")
    fecha_apertura = models.DateTimeField(
        auto_now_add=True, verbose_name="Fecha Apertura"
    )
    fecha_cierre = models.DateTimeField(
        null=True, blank=True, verbose_name="Fecha Cierre"
    )
    monto_inicial = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Monto Inicial (S/)",
    )
    monto_ventas_efectivo = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Ventas Efectivo (S/)",
    )
    monto_ventas_digital = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Ventas Digitales (S/)",
    )
    monto_esperado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Monto Esperado (S/)",
    )
    monto_real = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Monto Real / Contado (S/)",
    )
    diferencia = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Diferencia (S/)",
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS_CHOICES,
        default=ESTADO_ABIERTA,
        verbose_name="Estado de Caja",
    )
    observaciones = models.TextField(
        null=True, blank=True, verbose_name="Observaciones"
    )

    class Meta:
        db_table = "sesion_caja"
        managed = False
        verbose_name = "Sesión de Caja"
        verbose_name_plural = "Sesiones de Caja"
        ordering = ["-fecha_apertura"]

    def __str__(self):
        f_str = (
            self.fecha_apertura.strftime("%Y-%m-%d %H:%M")
            if self.fecha_apertura
            else ""
        )
        return f"Caja #{self.id} ({self.estado}) - Apertura: {f_str}"


class Pago(models.Model):
    """Registro transaccional de pagos multimoneda (PRB-51, PRB-55, PRB-56).

    Regla D7 (docs/db/DDL-OWNERSHIP.md): la tabla 'pago' es creada y
    gestionada exclusivamente por db/schema.sql en PostgreSQL (managed = False).
    """

    METODO_EFECTIVO = "EFECTIVO"
    METODO_YAPE = "YAPE"
    METODO_PLIN = "PLIN"
    METODO_TARJETA = "TARJETA"

    METODOS_CHOICES = [
        (METODO_EFECTIVO, "Efectivo"),
        (METODO_YAPE, "Yape"),
        (METODO_PLIN, "Plin"),
        (METODO_TARJETA, "Tarjeta"),
    ]

    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.RESTRICT,
        db_column="pedido_id",
        related_name="pagos",
        verbose_name="Pedido",
    )
    mesa = models.ForeignKey(
        Mesa,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        db_column="mesa_id",
        related_name="pagos",
        verbose_name="Mesa",
    )
    mozo_id = models.IntegerField(
        null=True, blank=True, db_column="mozo_id", verbose_name="ID Mozo"
    )
    sesion_caja = models.ForeignKey(
        SesionCaja,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="sesion_caja_id",
        related_name="pagos",
        verbose_name="Sesión de Caja",
    )
    metodo = models.CharField(
        max_length=20,
        choices=METODOS_CHOICES,
        verbose_name="Método de Pago",
    )
    monto = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Monto Pagado (S/)",
    )
    propina = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Propina (S/)",
    )
    referencia = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Nro. Referencia / Operación",
    )
    client_request_id = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="UUID Idempotencia",
    )
    fecha_pago = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Pago",
    )

    class Meta:
        db_table = "pago"
        managed = False
        verbose_name = "Pago"
        verbose_name_plural = "Pagos"
        ordering = ["-fecha_pago"]

    def __str__(self):
        origen = f"Mesa {self.mesa.numero}" if self.mesa else "Para llevar"
        return f"Pago #{self.id} ({self.metodo}) - S/ {self.monto} ({origen})"


class DetallePedido(models.Model):
    """Ítem o línea de plato dentro de una comanda con estado individual (PRB-57, PRB-59, PRB-86).

    Regla D7 (docs/db/DDL-OWNERSHIP.md): la tabla 'detalle_pedido' es creada y
    gestionada exclusivamente por db/schema.sql en PostgreSQL (managed = False).
    """

    ESTADO_ITEM_PENDIENTE = "PENDIENTE"
    ESTADO_ITEM_COCINANDO = "COCINANDO"
    ESTADO_ITEM_EN_PREPARACION = "EN_PREPARACION"
    ESTADO_ITEM_LISTO = "LISTO"
    ESTADO_ITEM_SERVIDO = "SERVIDO"
    ESTADO_ITEM_ANULADO = "ANULADO"

    ESTADOS_ITEM_CHOICES = [
        (ESTADO_ITEM_PENDIENTE, "Pendiente"),
        (ESTADO_ITEM_COCINANDO, "En Cocina"),
        (ESTADO_ITEM_EN_PREPARACION, "En Preparación"),
        (ESTADO_ITEM_LISTO, "Listo"),
        (ESTADO_ITEM_SERVIDO, "Servido"),
        (ESTADO_ITEM_ANULADO, "Anulado"),
    ]

    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        db_column="pedido_id",
        related_name="detalles",
        verbose_name="Pedido",
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.RESTRICT,
        db_column="producto_id",
        related_name="detalles_pedido",
        verbose_name="Producto",
    )
    precio_unitario = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Precio Unitario (S/)",
    )
    cantidad = models.IntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Cantidad",
    )
    notas = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Notas",
    )
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Subtotal (S/)",
    )
    estado_item = models.CharField(
        max_length=20,
        choices=ESTADOS_ITEM_CHOICES,
        default=ESTADO_ITEM_PENDIENTE,
        db_column="estado_item",
        verbose_name="Estado del Ítem",
    )
    estacion_item = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        db_column="estacion",
        verbose_name="Estación Asignada",
    )
    anulado_motivo = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_column="anulado_motivo",
        verbose_name="Motivo de Anulación",
    )

    class Meta:
        db_table = "detalle_pedido"
        managed = False
        verbose_name = "Detalle de Pedido"
        verbose_name_plural = "Detalles de Pedido"
        ordering = ["id"]

    @property
    def estado(self):
        """Alias para interoperabilidad con contratos API y serializadores."""
        return self.estado_item

    @estado.setter
    def estado(self, valor):
        self.estado_item = valor

    @property
    def estacion(self):
        """Estación de cocina correspondiente a este ítem."""
        return self.estacion_item or self.producto.estacion

    @estacion.setter
    def estacion(self, valor):
        self.estacion_item = valor

    @property
    def estacion_display(self):
        """Nombre legible de la estación de cocina."""
        return self.producto.estacion_display

    def __str__(self):
        return (
            f"{self.cantidad}x {self.producto.nombre} "
            f"[{self.estado_item}] (Pedido #{self.pedido_id})"
        )


class MovimientoStock(models.Model):
    """Registro auditable de stock diario, descuentos por venta y reversiones (PRB-59).

    Regla D7 (docs/db/DDL-OWNERSHIP.md): la tabla 'movimiento_stock' es creada y
    gestionada exclusivamente por db/schema.sql en PostgreSQL (managed = False).
    """

    TIPO_CARGA_DIARIA = "CARGA_DIARIA"
    TIPO_SALIDA_VENTA = "SALIDA_VENTA"
    TIPO_REVERSION = "REVERSION"
    TIPO_AJUSTE = "AJUSTE"

    TIPOS_CHOICES = [
        (TIPO_CARGA_DIARIA, "Carga diaria"),
        (TIPO_SALIDA_VENTA, "Salida por pedido"),
        (TIPO_REVERSION, "Reversión por anulación"),
        (TIPO_AJUSTE, "Ajuste manual"),
    ]

    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        db_column="producto_id",
        related_name="movimientos_stock",
        verbose_name="Plato",
    )
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="pedido_id",
        related_name="movimientos_stock",
        verbose_name="Pedido asociado",
    )
    tipo = models.CharField(
        max_length=20,
        choices=TIPOS_CHOICES,
        verbose_name="Tipo de movimiento",
    )
    cantidad = models.IntegerField(
        validators=[MinValueValidator(0)],
        verbose_name="Cantidad",
    )
    stock_anterior = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Stock anterior",
    )
    stock_resultante = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="Stock resultante",
    )
    motivo = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Motivo / Referencia",
    )
    registrado_por = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Registrado por",
    )
    fecha = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha y hora",
    )

    class Meta:
        db_table = "movimiento_stock"
        managed = False
        verbose_name = "Movimiento de Stock"
        verbose_name_plural = "Movimientos de Stock"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        res = (
            "Ilimitado"
            if self.stock_resultante is None
            else f"{self.stock_resultante} porc."
        )
        return f"[{self.tipo}] {self.producto.nombre}: {self.cantidad} -> {res}"


class EventoPedido(models.Model):
    """Auditoría inmutable de transiciones y eventos de comanda (PRB-53 / PRB-57).

    Regla D7 (docs/db/DDL-OWNERSHIP.md): la tabla 'evento_pedido' es creada y
    gestionada exclusivamente por db/schema.sql en PostgreSQL (managed = False).
    """

    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        db_column="pedido_id",
        related_name="eventos",
        verbose_name="Pedido",
    )
    estado_anterior = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="Estado Anterior",
    )
    estado_nuevo = models.CharField(
        max_length=20,
        verbose_name="Estado Nuevo",
    )
    usuario_id = models.IntegerField(
        null=True,
        blank=True,
        db_column="usuario_id",
        verbose_name="ID de Usuario / Personal",
    )
    motivo = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Motivo / Detalle",
    )
    fecha = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha y Hora",
    )

    class Meta:
        db_table = "evento_pedido"
        managed = False
        verbose_name = "Evento de Pedido"
        verbose_name_plural = "Eventos de Pedido"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        transicion = f"{self.estado_anterior} -> {self.estado_nuevo}"
        return f"Pedido #{self.pedido_id}: {transicion} ({self.fecha})"


class Rol(models.Model):
    """Rol operativo del personal en la tabla compartida 'rol' (PRB-52 / D7).

    Regla D7 (docs/db/DDL-OWNERSHIP.md): la tabla 'rol' es gestionada
    exclusivamente por db/schema.sql en PostgreSQL (managed = False).
    """

    ROL_ADMIN = "ADMIN"
    ROL_MOZO = "MOZO"
    ROL_COCINERO = "COCINERO"
    ROL_CAJERO = "CAJERO"

    ROLES_CANONICOS = (ROL_ADMIN, ROL_MOZO, ROL_COCINERO, ROL_CAJERO)

    nombre = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Nombre del Rol",
    )

    class Meta:
        db_table = "rol"
        managed = False
        verbose_name = "Rol Operativo"
        verbose_name_plural = "Roles Operativos"
        ordering = ["id"]

    def __str__(self):
        return self.nombre


class Usuario(models.Model):
    """Usuario operativo del POS compartido con Spring Boot (PRB-52 / D7 / D8).

    Regla D7: tabla 'usuario' administrada por db/schema.sql (managed = False).
    Regla D8: tanto 'clave_hash' como 'pin_hash' almacenan únicamente hashes
    BCrypt cost 10 ($2b$10$...), compatibles con BCryptPasswordEncoder de Java.
    """

    PATRON_PIN = re.compile(r"^\d{4}$")

    username = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Usuario operativo",
    )
    clave_hash = models.CharField(
        max_length=255,
        verbose_name="Hash BCrypt de contraseña",
    )
    pin_hash = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Hash BCrypt de PIN (4 dígitos)",
    )
    intentos_fallidos = models.IntegerField(
        default=0,
        verbose_name="Intentos fallidos",
    )
    bloqueado_hasta = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Bloqueado hasta",
    )
    rol = models.ForeignKey(
        Rol,
        on_delete=models.RESTRICT,
        db_column="rol_id",
        related_name="usuarios",
        verbose_name="Rol",
    )

    class Meta:
        db_table = "usuario"
        managed = False
        verbose_name = "Usuario Operativo POS"
        verbose_name_plural = "Usuarios Operativos POS"
        ordering = ["rol_id", "username"]

    @property
    def tiene_pin(self):
        """Indica si la cuenta tiene un PIN BCrypt registrado."""
        return bool(self.pin_hash and self.pin_hash.startswith(("$2b$", "$2a$")))

    @property
    def esta_bloqueado(self):
        """Indica si el usuario se encuentra temporalmente bloqueado."""
        if not self.bloqueado_hasta:
            return False
        ahora = timezone.now()
        hasta = self.bloqueado_hasta
        if timezone.is_naive(hasta):
            hasta = timezone.make_aware(hasta, timezone.get_current_timezone())
        return hasta > ahora

    def set_password_bcrypt(self, raw_password):
        """Genera hash BCrypt cost 10 cumpliendo estrictamente la Regla D8."""
        if not raw_password or len(raw_password.strip()) < 8:
            raise ValidationError(
                "La contraseña operativa debe tener al menos 8 caracteres."
            )
        if raw_password.strip() == "password123":
            raise ValidationError(
                "No se permite la contraseña débil de demostración 'password123'."
            )
        self.clave_hash = bcrypt.hashpw(
            raw_password.encode("utf-8"),
            bcrypt.gensalt(rounds=10),
        ).decode("utf-8")

    def check_password_bcrypt(self, raw_password):
        """Verifica una contraseña en texto plano contra el hash BCrypt."""
        if not raw_password or not self.clave_hash:
            return False
        return bcrypt.checkpw(
            raw_password.encode("utf-8"),
            self.clave_hash.encode("utf-8"),
        )

    def set_pin_bcrypt(self, raw_pin):
        """Valida PIN numérico de 4 dígitos y almacena su hash BCrypt cost 10."""
        pin_limpio = (raw_pin or "").strip()
        if not self.PATRON_PIN.match(pin_limpio):
            raise ValidationError(
                "El PIN operativo debe contener exactamente 4 dígitos numéricos."
            )
        self.pin_hash = bcrypt.hashpw(
            pin_limpio.encode("utf-8"),
            bcrypt.gensalt(rounds=10),
        ).decode("utf-8")

    def check_pin_bcrypt(self, raw_pin):
        """Verifica un PIN de 4 dígitos contra pin_hash."""
        if not raw_pin or not self.pin_hash:
            return False
        return bcrypt.checkpw(
            raw_pin.strip().encode("utf-8"),
            self.pin_hash.encode("utf-8"),
        )

    def __str__(self):
        return f"{self.username} ({self.rol.nombre})"
