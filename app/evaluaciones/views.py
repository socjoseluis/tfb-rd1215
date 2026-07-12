from django.shortcuts import get_object_or_404, redirect, render

from .forms import EquipoForm
from .importador import importar_equipos
from .models import Equipo


def equipo_alta(request):
    if request.method == 'POST':
        form = EquipoForm(request.POST)
        if form.is_valid():
            equipo = form.save()
            return redirect('evaluaciones:equipo_detalle', pk=equipo.pk)
    else:
        form = EquipoForm()
    return render(request, 'evaluaciones/equipo_alta.html', {'form': form})


def equipo_detalle(request, pk):
    equipo = get_object_or_404(Equipo, pk=pk)
    return render(request, 'evaluaciones/equipo_detalle.html', {'equipo': equipo})


def equipo_importar(request):
    resultado = None
    if request.method == 'POST':
        fichero = request.FILES.get('fichero')
        if fichero is not None:
            resultado = importar_equipos(fichero, fichero.name)
    return render(request, 'evaluaciones/equipo_importar.html', {'resultado': resultado})
