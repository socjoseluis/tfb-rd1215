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

    def save(self, commit=True):
        # Quien da de alta el equipo a mano está respondiendo por sus tipos,
        # aunque no marque ninguno.
        equipo = super().save(commit=False)
        equipo.tipos_confirmados = True
        if commit:
            equipo.save()
            self.save_m2m()
        return equipo


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
