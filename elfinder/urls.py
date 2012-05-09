from django.conf.urls import patterns, include, url
from elfinder import views

urlpatterns = patterns('',
    url(r'^$', views.index, name="elfinder_index"),
    url(r'^connector/(?P<coll_id>\d+)/$', views.connector_view,
        name='elfinder_connector'),
)