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

    def __str__(self):
        return f"{self.nombre} (S/ {self.precio})"


class Mesa(models.Model):
    """Mesa del salón en primer o segundo piso.

    Regla D7 (docs/db/DDL-OWNERSHIP.md): la tabla 'mesa' es creada y
    gestionada exclusivamente por db/schema.sql en PostgreSQL (managed = False).
    """

    ESTADO_LIBRE = "LIBRE"
    ESTADO_ATENDIENDO = "ATENDIENDO"
    ESTADO_OCUPADA = "OCUPADA"
    ESTADO_PIDE_CUENTA = "PIDE_CUENTA"

    ESTADOS_CHOICES = [
        (ESTADO_LIBRE, "Libre"),
        (ESTADO_ATENDIENDO, "Atendiendo"),
        (ESTADO_OCUPADA, "Ocupada"),
        (ESTADO_PIDE_CUENTA, "Pide Cuenta"),
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
    mozo_id = models.IntegerField(
        null=True, blank=True, verbose_name="ID Mozo"
    )
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
    ESTADO_CANCELADO = "CANCELADO"

    ESTADOS_CHOICES = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_COCINANDO, "Cocinando"),
        (ESTADO_LISTO, "Listo"),
        (ESTADO_SERVIDO, "Servido"),
        (ESTADO_COBRADO, "Cobrado"),
        (ESTADO_CANCELADO, "Cancelado"),
    ]

    mesa = models.ForeignKey(
        Mesa,
        on_delete=models.RESTRICT,
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

    class Meta:
        db_table = "pedido"
        managed = False
        verbose_name = "Pedido / Comanda"
        verbose_name_plural = "Pedidos / Comandas"
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"Pedido #{self.id} (Mesa {self.mesa.numero}) - S/ {self.total}"


class Rol(models.Model):
    """Rol de usuario del sistema POS y backoffice (PRB-12).

    Regla D7 (docs/db/DDL-OWNERSHIP.md): la tabla 'rol' es creada y
    gestionada exclusivamente por db/schema.sql en PostgreSQL (managed = False).
    """

    ROL_ADMIN = "ADMIN"
    ROL_MOZO = "MOZO"
    ROL_CAJERO = "CAJERO"
    ROL_COCINERO = "COCINERO"

    ROLES_CHOICES = [
        (ROL_ADMIN, "Administrador"),
        (ROL_MOZO, "Mozo"),
        (ROL_CAJERO, "Cajero"),
        (ROL_COCINERO, "Cocinero"),
    ]

    ROLES_VALIDOS = {ROL_ADMIN, ROL_MOZO, ROL_CAJERO, ROL_COCINERO}

    nombre = models.CharField(
        max_length=50,
        unique=True,
        choices=ROLES_CHOICES,
        verbose_name="Nombre del rol",
    )

    class Meta:
        db_table = "rol"
        managed = False
        verbose_name = "Rol"
        verbose_name_plural = "Roles"
        ordering = ["id"]

    def __str__(self):
        return self.nombre


class Usuario(models.Model):
    """Usuario operativo o administrativo del restaurante (PRB-12).

    Regla D7 (docs/db/DDL-OWNERSHIP.md): la tabla 'usuario' es creada y
    gestionada exclusivamente por db/schema.sql en PostgreSQL (managed = False).
    La baja lógica (desactivación) se codifica con el prefijo '!INACTIVO!' sobre
    `clave_hash`, invalidando el hash BCrypt sin alterar el DDL compartido.
    """

    PREFIJO_INACTIVO = "!INACTIVO!"

    username = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Nombre de usuario",
    )
    clave_hash = models.CharField(
        max_length=255,
        verbose_name="Hash de contraseña",
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
        verbose_name = "Usuario del Sistema"
        verbose_name_plural = "Usuarios del Sistema"
        ordering = ["username"]

    @property
    def activo(self):
        """Indica si el usuario se encuentra activo para operar en el sistema."""
        return not (self.clave_hash or "").startswith(self.PREFIJO_INACTIVO)

    def desactivar(self):
        """Marca al usuario como inactivo preservando su hash original."""
        if self.activo:
            self.clave_hash = f"{self.PREFIJO_INACTIVO}{self.clave_hash or ''}"

    def activar(self):
        """Reactiva al usuario restaurando su hash original."""
        if not self.activo:
            self.clave_hash = (self.clave_hash or "")[len(self.PREFIJO_INACTIVO):]

    def __str__(self):
        estado_str = "Activo" if self.activo else "Inactivo"
        return f"{self.username} ({self.rol.nombre}) - {estado_str}"

