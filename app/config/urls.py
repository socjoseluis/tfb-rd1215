"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.urls import include, path
from django.views.generic import TemplateView

from evaluaciones.forms import AutenticacionForm

urlpatterns = [
    path('admin/', admin.site.urls),
    # Los buscadores lo piden sin sesión, así que queda fuera de la exigencia
    # de autenticación que impone LoginRequiredMiddleware al resto.
    path(
        'robots.txt',
        login_not_required(
            TemplateView.as_view(template_name='robots.txt', content_type='text/plain')
        ),
        name='robots',
    ),
    # Las dos vistas se declaran una a una en vez de incluir
    # django.contrib.auth.urls entero: ese include trae además el flujo de
    # recuperación de contraseña, y no hay servidor de correo que lo sirva.
    path(
        'cuentas/entrar/',
        auth_views.LoginView.as_view(
            template_name='evaluaciones/login.html',
            authentication_form=AutenticacionForm,
        ),
        name='login',
    ),
    path('cuentas/salir/', auth_views.LogoutView.as_view(), name='logout'),
    path('', include('evaluaciones.urls')),
]
