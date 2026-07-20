from django import forms

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

    def clean_codigo(self):
        codigo = self.cleaned_data['codigo'].strip()
        if not codigo:
            raise forms.ValidationError('El código no puede estar vacío.')
        return codigo
