from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import Equipo


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
