"""Formularios del módulo web de catálogo, precios y pesca del día (PRB-19)."""

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import Categoria, Producto


class CategoriaForm(forms.ModelForm):
    """Formulario para crear o editar categorías de la carta marina."""

    class Meta:
        model = Categoria
        fields = ["nombre"]
        widgets = {
            "nombre": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Ej. Ceviches y Tiraditos",
                    "maxlength": "100",
                    "autocomplete": "off",
                }
            ),
        }

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if not nombre:
            raise ValidationError("El nombre de la categoría es obligatorio.")
        qs = Categoria.objects.filter(nombre__iexact=nombre)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Ya existe una categoría con ese nombre.")
        return nombre


class ProductoForm(forms.ModelForm):
    """Formulario para alta y edición de platos marinos, precios y stock."""

    class Meta:
        model = Producto
        fields = [
            "nombre",
            "categoria",
            "descripcion",
            "precio",
            "disponible",
            "imagen_url",
        ]
        widgets = {
            "nombre": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Ej. Ceviche Mixto Especial",
                    "maxlength": "150",
                }
            ),
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-textarea",
                    "rows": 3,
                    "placeholder": (
                        "Ingredientes principales, corte de pescado o guarnición..."
                    ),
                }
            ),
            "precio": forms.NumberInput(
                attrs={
                    "class": "form-input",
                    "step": "0.10",
                    "min": "0.01",
                    "placeholder": "48.00",
                }
            ),
            "disponible": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "imagen_url": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "https://... (opcional)",
                }
            ),
        }

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if not nombre:
            raise ValidationError("El nombre del plato es obligatorio.")
        return nombre

    def clean_precio(self):
        precio = self.cleaned_data.get("precio")
        if precio is None or precio <= Decimal("0.00"):
            raise ValidationError("El precio debe ser mayor a S/ 0.00.")
        return precio.quantize(Decimal("0.01"))

    def clean_imagen_url(self):
        url = (self.cleaned_data.get("imagen_url") or "").strip()
        return url or None


class AperturaCajaForm(forms.Form):
    """Formulario para abrir un nuevo turno de caja con fondo inicial (PRB-60)."""

    monto_inicial = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("100.00"),
        label="Fondo inicial en efectivo (S/)",
        widget=forms.NumberInput(
            attrs={
                "class": "form-input",
                "step": "0.10",
                "min": "0.00",
                "placeholder": "100.00",
            }
        ),
    )
    observaciones = forms.CharField(
        required=False,
        max_length=500,
        label="Observaciones de apertura",
        widget=forms.Textarea(
            attrs={
                "class": "form-textarea",
                "rows": 2,
                "placeholder": "Ej. Turno tarde · Sencillo verificado en billetes y monedas...",
            }
        ),
    )

    def clean_monto_inicial(self):
        monto = self.cleaned_data.get("monto_inicial")
        if monto is None or not monto.is_finite() or monto < Decimal("0.00"):
            raise ValidationError("El monto inicial debe ser mayor o igual a S/ 0.00.")
        return monto.quantize(Decimal("0.01"))

    def clean_observaciones(self):
        return (self.cleaned_data.get("observaciones") or "").strip()


class CierreCajaForm(forms.Form):
    """Formulario de arqueo físico y Cierre Z de sesión de caja (PRB-60)."""

    monto_real = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        label="Efectivo físico contado en gaveta (S/)",
        widget=forms.NumberInput(
            attrs={
                "class": "form-input",
                "step": "0.10",
                "min": "0.00",
                "placeholder": "0.00",
            }
        ),
    )
    observaciones = forms.CharField(
        required=False,
        max_length=500,
        label="Observaciones / Justificación de arqueo",
        widget=forms.Textarea(
            attrs={
                "class": "form-textarea",
                "rows": 3,
                "placeholder": (
                    "Obligatorio si existe sobrante o faltante. "
                    "Ej. Faltante de S/ 2.00 por redondeo de vuelto en mesa 4..."
                ),
            }
        ),
    )

    def __init__(self, *args, monto_esperado=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.monto_esperado = (
            monto_esperado.quantize(Decimal("0.01"))
            if isinstance(monto_esperado, Decimal)
            else None
        )

    def clean_monto_real(self):
        monto = self.cleaned_data.get("monto_real")
        if monto is None or not monto.is_finite() or monto < Decimal("0.00"):
            raise ValidationError("El monto contado debe ser mayor o igual a S/ 0.00.")
        return monto.quantize(Decimal("0.01"))

    def clean_observaciones(self):
        return (self.cleaned_data.get("observaciones") or "").strip()

    def clean(self):
        cleaned = super().clean()
        monto_real = cleaned.get("monto_real")
        observaciones = cleaned.get("observaciones") or ""
        if monto_real is not None and self.monto_esperado is not None:
            diferencia = (monto_real - self.monto_esperado).quantize(Decimal("0.01"))
            cleaned["diferencia"] = diferencia
            if diferencia != Decimal("0.00") and not observaciones:
                tipo = "sobrante" if diferencia > Decimal("0.00") else "faltante"
                self.add_error(
                    "observaciones",
                    f"Se detectó un {tipo} de S/ {abs(diferencia):.2f}. "
                    "Debes registrar una observación explicando el descuadre "
                    "antes de cerrar la caja.",
                )
        return cleaned
