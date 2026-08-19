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
    # La dirección del QR se deja corta a propósito: es lo que se codifica en
    # la etiqueta, y cuanto más corto el texto, menos denso el dibujo y mejor
    # se lee con un móvil en planta.
    path('q/<uuid:token>/', views.equipo_publico, name='equipo_publico'),
    path('equipos/<int:pk>/qr/', views.equipo_qr, name='equipo_qr'),
    path('equipos/<int:pk>/documentos/subir/', views.documento_subir, name='documento_subir'),
    path('equipos/<int:pk>/documentos/no-procede/', views.exencion_nueva, name='exencion_nueva'),
    path('exenciones/<int:pk>/retirar/', views.exencion_retirar, name='exencion_retirar'),
    path('documentos/<int:pk>/', views.documento_descargar, name='documento_descargar'),
    path('documentos/<int:pk>/retirar/', views.documento_borrar, name='documento_borrar'),
    path('medidas/', views.medidas, name='medidas'),
    path('medidas/<int:pk>/estado/', views.medida_estado, name='medida_estado'),
    path('equipos/importar/', views.equipo_importar, name='equipo_importar'),
]
