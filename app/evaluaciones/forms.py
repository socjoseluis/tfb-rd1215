from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import Equipo, Medida


class EquipoForm(forms.ModelForm):
    class Meta:
        model = Equipo
        fields = [
            'codigo', 'nombre', 'marca_modelo', 'num_serie', 'anio', 'linea',
            'tipos',
        ]
        widgets = {
            'tipos': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Bootstrap exige sus clases en cada control. Las casillas de «tipos»
        # quedan fuera: llevan su propio marcado.
        for nombre, campo in self.fields.items():
            if nombre == 'tipos':
                continue
            if isinstance(campo.widget, forms.Select):
                campo.widget.attrs['class'] = 'form-select'
            else:
                campo.widget.attrs['class'] = 'form-control'

    def clean_codigo(self):
        codigo = self.cleaned_data['codigo'].strip()
        if not codigo:
            raise forms.ValidationError('El código no puede estar vacío.')
        return codigo


class EquipoTiposForm(forms.ModelForm):
    """Pantalla intermedia para los equipos que llegaron sin tipo.

    La importación por lotes no trae el tipo, así que se pregunta antes de
    la primera evaluación.
    """

    class Meta:
        model = Equipo
        fields = ['tipos']
        widgets = {
            'tipos': forms.CheckboxSelectMultiple,
        }

    def save(self, commit=True):
        equipo = super().save(commit=False)
        equipo.tipos_confirmados = True
        if commit:
            equipo.save()
            self.save_m2m()
        return equipo


class MedidaForm(forms.ModelForm):
    """Alta de una medida correctiva desde su evaluación (RF-06).

    La evaluación no es un campo: viene de la dirección, porque la medida se
    da de alta desde ella. Si se ofreciera, el desplegable listaría todas las
    evaluaciones de la base de datos.
    """

    class Meta:
        model = Medida
        fields = ['descripcion', 'no_conformidades', 'fecha_prevista', 'estado']
        widgets = {
            'no_conformidades': forms.CheckboxSelectMultiple,
            'descripcion': forms.Textarea(attrs={'rows': 3}),
            # Con type="date" el móvil abre el selector de fecha del sistema
            # en vez de un campo de texto (RNF-01).
            'fecha_prevista': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, evaluacion, **kwargs):
        super().__init__(*args, **kwargs)

        # Limitar las opciones no es solo decidir qué casillas se dibujan: es
        # también contra lo que Django valida el envío. Una respuesta de otra
        # evaluación, o conforme, se rechaza aunque se manipule el formulario.
        # Es la regla que el modelo no puede imponer.
        no_conformidades = self.fields['no_conformidades']
        no_conformidades.queryset = (
            evaluacion.respuestas
            .filter(resultado='NC')
            .select_related('criterio')
        )
        # Todas las opciones son no conformidades, así que arrastrar el
        # «→ No conforme» de Respuesta.__str__ a cada casilla no aporta nada.
        no_conformidades.label_from_instance = lambda r: r.criterio.enunciado

        for nombre, campo in self.fields.items():
            if nombre == 'no_conformidades':
                continue
            if isinstance(campo.widget, forms.Select):
                campo.widget.attrs['class'] = 'form-select'
            else:
                campo.widget.attrs['class'] = 'form-control'


class AutenticacionForm(AuthenticationForm):
    """Formulario de entrada a la aplicación.

    La comprobación de las credenciales se hereda entera de Django; lo único
    que se añade son las clases que Bootstrap exige en cada control, igual
    que en EquipoForm.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs['class'] = 'form-control'
