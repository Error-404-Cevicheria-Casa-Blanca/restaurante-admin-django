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
