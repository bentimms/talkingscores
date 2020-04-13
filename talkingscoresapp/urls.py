from django.urls import path
from django.views.generic.base import TemplateView
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('score/<id>/<filename>', views.score, name='score'),
    path('score_options/<id>/<filename>', views.options, name='options'),
    path('process/<id>/<filename>', views.process, name='process'),
    path('oops/<id>/<filename>', views.error, name='error'),
    path('midis/<id>/<filename>',views.midi, name="midi" ),
    path("robots.txt", TemplateView.as_view(template_name="robots.txt", content_type="text/plain"), ),
]