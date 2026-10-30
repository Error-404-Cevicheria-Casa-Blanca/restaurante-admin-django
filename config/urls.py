"""URL configuration for config project."""

from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "La Casa Blanca · Administración"
admin.site.site_title = "La Casa Blanca Admin"
admin.site.index_title = "Gestión técnica de modelos"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("catalogo.urls")),
]
