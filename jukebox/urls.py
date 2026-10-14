"""Project-level URL Configuration for Office Jukebox."""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("music.urls")),
]
