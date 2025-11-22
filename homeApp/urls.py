from django.urls import path
from homeApp import views
from . import views

urlpatterns = [
    path("", views.HomeView.as_view(), name="Home"),
    path("gestor-ordenes/", views.gestor_ordenes_view, name="gestor_ordenes"),
    path("portal-tecnico/", views.portal_tecnico_view, name="portal_tecnico"),
]
