from django.conf.urls import patterns, include, url
from elfinder import views


urlpatterns = patterns('',
    url(r'^(?P<root>\d+)/$', views.index, name="index"),
    url(r'^connector/(?P<root>\d+)/$', views.connector,
        name='connector'),
)
