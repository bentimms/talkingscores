from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('score/<id>/<filename>', views.score, name='score'),
    path('score_options/<id>/<filename>', views.options, name='options'),
    path('process/<id>/<filename>', views.process, name='process'),
    path('oops/<id>/<filename>', views.error, name='error'),

]
# patterns('',
# ) + static('/scores', document_root=os.path.join(settings.BASE_DIR,settings.STATIC_ROOT, 'data'))