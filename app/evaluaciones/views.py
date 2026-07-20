from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import EquipoForm, EquipoTiposForm
from .importador import importar_equipos
from .models import Criterio, Equipo, Evaluacion, Respuesta


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


def equipo_tipos(request, pk):
    equipo = get_object_or_404(Equipo, pk=pk)
    # Si se llega aquí desde el intento de evaluar, hay que volver allí.
    evaluar = '1' in (request.GET.get('evaluar'), request.POST.get('evaluar'))

    if request.method == 'POST':
        form = EquipoTiposForm(request.POST, instance=equipo)
        if form.is_valid():
            form.save()
            if evaluar:
                return redirect('evaluaciones:evaluacion_nueva', pk=equipo.pk)
            return redirect('evaluaciones:equipo_detalle', pk=equipo.pk)
    else:
        form = EquipoTiposForm(instance=equipo)

    return render(request, 'evaluaciones/equipo_tipos.html', {
        'equipo': equipo,
        'form': form,
        'evaluar': evaluar,
    })


def evaluacion_nueva(request, pk):
    equipo = get_object_or_404(Equipo, pk=pk)

    # Los equipos importados por lotes llegan sin tipo: hay que preguntarlo
    # antes de evaluar, porque de él dependen los criterios aplicables.
    if not equipo.tipos_confirmados:
        url = reverse('evaluaciones:equipo_tipos', kwargs={'pk': equipo.pk})
        return redirect(f'{url}?evaluar=1')

    criterios = list(
        Criterio.objects.filter(grupo__in=equipo.grupos_aplicables())
    )

    RespuestaFormSet = modelformset_factory(
        Respuesta,
        fields=['criterio', 'resultado', 'indicaciones'],
        extra=len(criterios),
    )

    if request.method == 'POST':
        formset = RespuestaFormSet(
            request.POST,
            queryset=Respuesta.objects.none(),
        )
        if formset.is_valid():
            evaluacion = Evaluacion.objects.create(equipo=equipo)
            for respuesta in formset.save(commit=False):
                respuesta.evaluacion = evaluacion
                respuesta.save()
            return redirect('evaluaciones:evaluacion_detalle', pk=evaluacion.pk)
    else:
        formset = RespuestaFormSet(
            queryset=Respuesta.objects.none(),
            initial=[{'criterio': c} for c in criterios],
        )

    return render(request, 'evaluaciones/evaluacion_nueva.html', {
        'equipo': equipo,
        'formset': formset,
        'filas': zip(formset, criterios),
    })


def evaluacion_detalle(request, pk):
    evaluacion = get_object_or_404(Evaluacion, pk=pk)
    respuestas = (
        evaluacion.respuestas
        .select_related('criterio__grupo')
        .order_by('criterio__grupo__orden', 'criterio__orden')
    )
    return render(request, 'evaluaciones/evaluacion_detalle.html', {
        'evaluacion': evaluacion,
        'respuestas': respuestas,
    })
