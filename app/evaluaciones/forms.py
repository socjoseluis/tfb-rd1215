from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import (
    Documento, Equipo, ExencionDocumental, Incidencia, Medida,
)


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


class DocumentoForm(forms.ModelForm):
    """Subida de un documento a la ficha de un equipo (RF-09).

    El equipo no es un campo: viene de la dirección, igual que la evaluación
    en MedidaForm. Sí hace falta conocerlo para rechazar un tipo que se haya
    declarado «no procede» en ese equipo.
    """

    EXTENSIONES = ('.pdf', '.jpg', '.jpeg', '.png')
    TAMANO_MAXIMO = 25 * 1024 * 1024  # 25 MB

    class Meta:
        model = Documento
        fields = ['tipo', 'tipo_otro', 'titulo', 'fichero', 'publico']

    def __init__(self, *args, equipo, **kwargs):
        self.equipo = equipo
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            if isinstance(campo.widget, forms.CheckboxInput):
                # Bootstrap pide otra clase para las casillas: con
                # form-control se dibujaría como un cuadro de texto.
                campo.widget.attrs['class'] = 'form-check-input'
            elif isinstance(campo.widget, forms.Select):
                campo.widget.attrs['class'] = 'form-select'
            else:
                campo.widget.attrs['class'] = 'form-control'

    def clean_fichero(self):
        """Límites de la subida: qué formatos y qué tamaño.

        Sin tope de tamaño, un solo fichero puede llenar el disco del
        servidor; sin lista de formatos, la aplicación se convierte en
        alojamiento de ficheros arbitrarios servidos desde su propio
        dominio.

        Se comprueba la extensión, no el contenido: un fichero puede
        llamarse .pdf y ser otra cosa. Comprobar el contenido de verdad
        exigiría una biblioteca aparte, y aquí lo que contiene la subida
        nunca se ejecuta ni se interpreta, solo se entrega tal cual.
        """
        fichero = self.cleaned_data['fichero']

        nombre = fichero.name.lower()
        if not nombre.endswith(self.EXTENSIONES):
            raise forms.ValidationError(
                'Formato no admitido. Suba un PDF o una imagen '
                '(%s).' % ', '.join(self.EXTENSIONES)
            )

        if fichero.size > self.TAMANO_MAXIMO:
            raise forms.ValidationError(
                'El fichero ocupa %.1f MB y el máximo son %d MB.'
                % (fichero.size / 1024 / 1024, self.TAMANO_MAXIMO / 1024 / 1024)
            )

        return fichero

    def clean(self):
        """La regla que el modelo no puede imponer.

        Un campo obligatorio solo cuando otro vale algo concreto no se puede
        declarar en el modelo, así que se comprueba aquí: al elegir «Otro»
        hay que decir de qué se trata, o en la consulta en campo el
        documento aparecería como «Otro» y no informaría de nada.
        """
        datos = super().clean()
        if datos.get('tipo') == 'OT' and not datos.get('tipo_otro', '').strip():
            self.add_error(
                'tipo_otro',
                'Indique de qué documento se trata al elegir «Otro».',
            )

        # Un documento de un tipo declarado «no procede» deja al equipo
        # diciendo dos cosas contrarias a la vez, y el aviso de evidencia
        # documental se apagaría por la exención mientras el documento está
        # ahí. Se corta aquí y se dice cuál de las dos hay que retirar.
        tipo = datos.get('tipo')
        if tipo and tipo in self.equipo.tipos_eximidos:
            self.add_error(
                'tipo',
                'Este equipo tiene declarado que ese documento no procede. '
                'Retire primero esa declaración desde la ficha del equipo.',
            )
        return datos


class IncidenciaForm(forms.ModelForm):
    """Registro de una incidencia sobre un equipo (RF-07).

    El equipo viene de la dirección, como en las demás altas que cuelgan de
    una ficha. La fecha se ofrece porque una incidencia se registra a menudo
    después de ocurrir: quien vuelve del taller la anota al día siguiente.
    """

    class Meta:
        model = Incidencia
        fields = ['descripcion', 'fecha']
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 3}),
            # Con type="datetime-local" el móvil abre el selector del
            # sistema en vez de un campo de texto (RNF-01).
            'fecha': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs['class'] = 'form-control'

    def clean_descripcion(self):
        descripcion = self.cleaned_data['descripcion'].strip()
        if not descripcion:
            raise forms.ValidationError(
                'Describa qué ha ocurrido: una incidencia sin descripción '
                'marca la evaluación para revisión sin decir por qué.'
            )
        return descripcion


class ExencionForm(forms.ModelForm):
    """Declarar que un tipo de documento no procede en un equipo.

    Los tipos que se pueden eximir los limita el modelo. Lo que se limita
    aquí es otra cosa: los que ya están eximidos en ESTE equipo, para no
    ofrecer una declaración que la restricción de unicidad rechazaría
    después con un error de base de datos en vez de uno de formulario.
    """

    class Meta:
        model = ExencionDocumental
        fields = ['tipo', 'motivo']
        widgets = {
            'motivo': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, equipo, **kwargs):
        super().__init__(*args, **kwargs)

        # Se retiran los tipos ya eximidos, para no ofrecer una declaración
        # que la restricción de unicidad rechazaría después con un error de
        # base de datos, y los que el equipo ya tiene subidos: declarar que no
        # procede algo que está ahí es contradecirse.
        self.equipo = equipo
        fuera = equipo.tipos_eximidos | {
            documento.tipo for documento in equipo.documentos.all()
        }
        self.fields['tipo'].choices = [
            (codigo, nombre)
            for codigo, nombre in self.fields['tipo'].choices
            if codigo not in fuera
        ]

        for campo in self.fields.values():
            if isinstance(campo.widget, forms.Select):
                campo.widget.attrs['class'] = 'form-select'
            else:
                campo.widget.attrs['class'] = 'form-control'

    def clean_motivo(self):
        motivo = self.cleaned_data['motivo'].strip()
        if not motivo:
            raise forms.ValidationError(
                'El motivo es obligatorio: sin él, la exención sería un modo '
                'de ocultar el aviso en vez de justificarlo.'
            )
        return motivo


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
