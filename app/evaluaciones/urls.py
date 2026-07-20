from django.urls import path

from . import views

app_name = 'evaluaciones'

urlpatterns = [
    path('equipos/alta/', views.equipo_alta, name='equipo_alta'),
    path('equipos/<int:pk>/', views.equipo_detalle, name='equipo_detalle'),
    path('equipos/<int:pk>/evaluar/', views.evaluacion_nueva, name='evaluacion_nueva'),
    path('equipos/importar/', views.equipo_importar, name='equipo_importar'),
]
