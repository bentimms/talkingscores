from django.urls import path
from django.views.generic.base import TemplateView
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('change-log', views.change_log, name='change-log'),
    path('contact-us', views.contact_us, name='contact-us'),
    path('privacy-policy', views.privacy_policy, name='privacy-policy'),
    path('score/<id>/<filename>', views.score, name='score'),
    path('score_options/<id>/<filename>', views.options, name='options'),
    path('process/<id>/<filename>', views.process, name='process'),
    path('oops/<id>/<filename>', views.error, name='error'),
    path('midis/<id>/<filename>',views.midi, name="midi" ),
    path("robots.txt", TemplateView.as_view(template_name="robots.txt", content_type="text/plain"), ),
    path("sitemap.xml", TemplateView.as_view(template_name="sitemap.xml", content_type="text/xml"), ),
]