from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models


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

    class Meta:
        db_table = "pedido"
        managed = False
        verbose_name = "Pedido / Comanda"
        verbose_name_plural = "Pedidos / Comandas"
        ordering = ["-fecha_creacion"]

    def __str__(self):
        origen = f"Mesa {self.mesa.numero}" if self.mesa else "Para llevar"
        return f"Pedido #{self.id} ({origen}) - S/ {self.total}"


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
    """Ítem o línea de plato dentro de una comanda (PRB-59).

    Regla D7 (docs/db/DDL-OWNERSHIP.md): la tabla 'detalle_pedido' es creada y
    gestionada exclusivamente por db/schema.sql en PostgreSQL (managed = False).
    """

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

    class Meta:
        db_table = "detalle_pedido"
        managed = False
        verbose_name = "Detalle de Pedido"
        verbose_name_plural = "Detalles de Pedido"
        ordering = ["id"]

    def __str__(self):
        return f"{self.cantidad}x {self.producto.nombre} (Pedido #{self.pedido_id})"


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
