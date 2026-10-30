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
            "disponible": forms.CheckboxInput(
                attrs={"class": "form-checkbox"}
            ),
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
