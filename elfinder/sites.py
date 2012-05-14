from functools import update_wrapper
from django.core.urlresolvers import reverse
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.utils.translation import ugettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect


class ElfinderSite(object):
    index_template = 'elfinder/base.html'
    title = 'File manager'

    def __init__(self, finderDriver, name='elfinder', app_name='elfinder'):
        self.driver = finderDriver
        self.name = name
        self.app_name = app_name

    def manage_view(self, view, cacheable=False):
        """
        Decorator to create a view attached to this ``ElfinderSite``
        (copied from django AdminSite). This
        wraps the view and provides permission checking by calling
        ``self.has_permission``
        """
        def inner(request, *args, **kwargs):
            if not self.has_permission(request):
                # mantain admin login and logout for the moment
                index_path = reverse('admin:index', current_app=self.name)
                return HttpResponseRedirect(index_path)
            return view(request, *args, **kwargs)
        if not cacheable:
            inner = never_cache(inner)
        # We add csrf_protect here so this function can be used as a utility
        # function for any view, without having to repeat 'csrf_protect'.
        if not getattr(view, 'csrf_exempt', False):
            inner = csrf_protect(inner)
        return update_wrapper(inner, view)

    def get_urls(self):
        from django.conf.urls import patterns, url, include

        def wrap(view, cacheable=False):
            """
            This function is used in admin site to provide site-wide permissions
            on the view.
            """
            def wrapper(*args, **kwargs):
                return self.manage_view(view, cacheable)(*args, **kwargs)
            return update_wrapper(wrapper, view)

        # Admin-site-wide views.
        urlpatterns = patterns('',
            url(r'^$',
                wrap(self.index),
                name='index'),
            url(r'^connector/$',
                wrap(self.connector),
                name='connector'),
        )
        return urlpatterns

    @property
    def urls(self):
        return self.get_urls(), self.app_name, self.name

    def has_permission(self, request):
        return True

    def index(self, request, extra_context=None):
        context = {
            'title': self.title,
        }
        if extra_context:
            context.update(extra_context)
        return TemplateResponse(request, self.index_template, context)

    def connector(self, request, extra_context):
        return {}