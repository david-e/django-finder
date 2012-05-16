import inspect
import logging
import simplejson as json
from functools import update_wrapper

from django.core.urlresolvers import reverse
from django.http import Http404, HttpResponseRedirect, HttpResponse
from django.template.response import TemplateResponse
from django.utils.translation import ugettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from elfinder.drivers.base import FinderDriver

# Get an instance of a logger
logger = logging.getLogger(__name__)

class ElfinderSite(object):
    index_template = 'elfinder/base.html'
    title = 'File manager'
    _options = {
        'ui_options': {
            'toolbar': [
                ['back', 'forward'],
                ['download', 'mkdir', 'mkfile', 'upload'],
                ['copy', 'cut', 'paste'],
                ['rm'],
                ['rename'],
                ['view'],
            ]
        },
        'context_menu': {
            'navbar': ['open', '|', 'copy', 'cut', 'paste', '|', 'rm'],
            'cwd': ['reload', 'back', '|', 'mkdir', 'mkfile', 'paste' '|',
                    'upload'],
            'files': ['edit', 'open', '|', 'copy', 'cut', 'paste', '|',
                  'rm', 'rename']
        },
        'init_params': {
            'api': '2.0',
            'uplMaxSize': '1024M', 
            'options': {
                'separator': '/',
                'disabled': [],
                'archivers': {'create': [], 'extract': []},
                'copyOverwrite': 1,
            }
        },
        'allowed_http_params': ['cmd', 'target', 'targets[]', 'current', 'tree',
                'name', 'content', 'src', 'dst', 'cut', 'init',
                'type', 'width', 'height', 'upload[]'
        ]
    }

    def __init__(self, finderDriver=None,
                 name='elfinder', app_name='elfinder',
                 ui_options={}, context_menu={}, init_params={},
                 allowed_http_params=[]):
        self.driver = finderDriver or FinderDriver()
        self.name = name
        self.app_name = app_name
        # options dictionary based on default_options
        self.ui_options = dict(
            self._options['ui_options'], **ui_options)
        self.context_menu = dict(
            self._options['context_menu'], **context_menu)
        self.init_params = dict(
            self._options['init_params'], **init_params)
        self.allowed_http_params = (allowed_http_params or
            self._options['allowed_http_params'])

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

    def error_response(self, message):
        return self._create_connector_response({'error': message})

    def _create_response(self, content,
        status_code=200,  mimetype='application/json',):
        response = HttpResponse(mimetype = mimetype)
        response.status_code = status_code
        if mimetype == 'application/json':
            content = json.dumps(content)
        response.content = content
        return response
    
    def index(self, request, extra_context=None):
        context = {
            'title': self.title,
            'contextmenu': self.context_menu,
            'uiOptions': self.ui_options,
        }
        if extra_context:
            context.update(extra_context)
        return TemplateResponse(request, self.index_template, context)

    def run_command(self, cmd, **data):
        # pick the driver function from commands dictionary
        driver_func = getattr(self.driver, self.driver.commands[cmd])
        args, _, _, defaults = inspect.getargspec(driver_func)
        # driver_func accept only args and defaults
        index = len(args) - len(defaults) # index of args with defaults
        params = {}
        for arg in args:
            if arg is 'self':
                continue
            # arg present in data
            if arg in data:
                params[arg] = data[arg]
                continue
            # means mandatory argument and no default value present
            if args.index(arg) < index:
               raise Exception(
                   'mandatory argument %s missing in command %s' % (arg, cmd))
        # call the driver function with parameters of the request
        content = driver_func(**params)
        if 'init' in data:
            content.update(self.init_params)
        return content

    def connector(self, request, extra_context=None):
        data_src = request.POST or request.GET
        # fill the data dict, needed to execute the command
        data = {'user': request.user}
         # Copy allowed parameters from the given request's GET to self.data
        for field in self.allowed_http_params:
            if field in data_src:
                if field == "targets[]":
                    data[field] = data_src.getlist(field)
                else:
                    data[field] = data_src[field]
        print data
        if not 'cmd' in data:
            return error_response('no cmd paramater found in the request')
        # check if 'cmd' is available in the driver and run it
        cmd = data.pop('cmd')
        if not cmd in self.driver.commands:
            return self.error_response(
                'command %s not available with this driver' % cmd)
        try:
            content = self.run_command(cmd, **data)
        except Exception as e:
            return self.error_response(e)
        print content
        return self._create_response(content)