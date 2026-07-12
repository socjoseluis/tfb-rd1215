from django.contrib import admin

from .models import Criterio, Equipo, Evaluacion, GrupoCriterio, Linea, Respuesta

admin.site.register(Linea)
admin.site.register(Equipo)
admin.site.register(GrupoCriterio)
admin.site.register(Criterio)
admin.site.register(Evaluacion)
admin.site.register(Respuesta)
