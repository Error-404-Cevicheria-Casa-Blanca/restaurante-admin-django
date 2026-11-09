"""Formularios del módulo web de catálogo, precios y pesca del día (PRB-19)."""

from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError

from .models import Categoria, Producto, Rol, Usuario


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


def sincronizar_acceso_panel_django(
    usuario,
    raw_password=None,
    username_anterior=None,
):
    """Sincroniza el usuario del sistema con auth_user para el acceso al panel (PRB-12).

    - Rol ADMIN activo -> is_staff=True, is_active=True (puede ingresar al panel).
    - Roles MOZO, CAJERO, COCINERO -> is_staff=False (no pueden ingresar al panel).
    - Usuario desactivado -> is_active=False, is_staff=False.
    """
    User = get_user_model()
    es_admin = usuario.rol.nombre == Rol.ROL_ADMIN
    esta_activo = usuario.activo

    auth_user = None
    if username_anterior and username_anterior != usuario.username:
        auth_user = User.objects.filter(username=username_anterior).first()
    if auth_user is None:
        auth_user = User.objects.filter(username=usuario.username).first()

    if auth_user is None:
        auth_user = User(username=usuario.username)
        if raw_password:
            auth_user.set_password(raw_password)
        else:
            auth_user.set_unusable_password()
    else:
        auth_user.username = usuario.username
        if raw_password:
            auth_user.set_password(raw_password)

    auth_user.is_active = esta_activo
    auth_user.is_staff = bool(es_admin and esta_activo)
    auth_user.save()
    return auth_user


class UsuarioForm(forms.ModelForm):
    """Formulario de alta y edición de usuarios del sistema y asignación de rol (PRB-12)."""

    password = forms.CharField(
        required=False,
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "Mínimo 6 caracteres",
                "autocomplete": "new-password",
            }
        ),
    )
    activo = forms.BooleanField(
        required=False,
        initial=True,
        label="Usuario activo",
        widget=forms.CheckboxInput(attrs={"class": "form-checkbox"}),
    )

    class Meta:
        model = Usuario
        fields = ["username", "rol"]
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Ej. mozo_salon01",
                    "maxlength": "50",
                    "autocomplete": "off",
                }
            ),
            "rol": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].required = False
        self.fields["rol"].required = False
        if self.instance and self.instance.pk:
            self.fields["activo"].initial = self.instance.activo
        else:
            self.fields["activo"].initial = True

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise ValidationError("El nombre de usuario es obligatorio.")
        if " " in username:
            raise ValidationError("El nombre de usuario no puede contener espacios.")
        qs = Usuario.objects.filter(username__iexact=username)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Ya existe un usuario con ese nombre de usuario.")
        return username

    def clean_rol(self):
        rol = self.cleaned_data.get("rol")
        if rol is None:
            raise ValidationError("Debe asignar un rol válido al usuario.")
        if rol.nombre not in Rol.ROLES_VALIDOS:
            raise ValidationError("El rol seleccionado no pertenece a los roles permitidos.")
        return rol

    def clean_password(self):
        password = self.cleaned_data.get("password") or ""
        es_edicion = bool(self.instance and self.instance.pk)
        if not es_edicion and not password:
            raise ValidationError("La contraseña es obligatoria al crear un usuario.")
        if password and len(password) < 6:
            raise ValidationError("La contraseña debe tener al menos 6 caracteres.")
        return password

    def save(self, commit=True):
        es_edicion = bool(self.instance and self.instance.pk)
        username_anterior = None
        if es_edicion:
            previo = Usuario.objects.filter(pk=self.instance.pk).first()
            if previo:
                username_anterior = previo.username

        usuario = super().save(commit=False)
        raw_password = self.cleaned_data.get("password")
        activo = bool(self.cleaned_data.get("activo"))

        if raw_password:
            usuario.clave_hash = make_password(raw_password)
        elif not usuario.clave_hash:
            usuario.clave_hash = make_password(None)

        if activo:
            usuario.activar()
        else:
            usuario.desactivar()

        if commit:
            usuario.save()
            sincronizar_acceso_panel_django(
                usuario,
                raw_password=raw_password or None,
                username_anterior=username_anterior,
            )
        return usuario

