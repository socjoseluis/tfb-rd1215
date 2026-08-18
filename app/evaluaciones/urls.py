from django.urls import path

from . import views

app_name = 'evaluaciones'

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('equipos/alta/', views.equipo_alta, name='equipo_alta'),
    path('equipos/<int:pk>/', views.equipo_detalle, name='equipo_detalle'),
    path('equipos/<int:pk>/editar/', views.equipo_editar, name='equipo_editar'),
    path('equipos/<int:pk>/tipos/', views.equipo_tipos, name='equipo_tipos'),
    path('equipos/<int:pk>/evaluar/', views.evaluacion_nueva, name='evaluacion_nueva'),
    path('evaluaciones/<int:pk>/', views.evaluacion_detalle, name='evaluacion_detalle'),
    path('evaluaciones/<int:pk>/medidas/nueva/', views.medida_nueva, name='medida_nueva'),
    path('medidas/', views.medidas, name='medidas'),
    path('medidas/<int:pk>/estado/', views.medida_estado, name='medida_estado'),
    path('equipos/importar/', views.equipo_importar, name='equipo_importar'),
]
