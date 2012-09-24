from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import ugettext_lazy as _

import inspect
import json
import logging

from elfinder import params
from elfinder.drivers.base import FinderDriver


def _ajax(content, status=200, mimetype='application/json', 
          encode_func=json.dumps):
    """
    Create an HttpResponse with content encoded by encode_func
    """
    return HttpResponse(mimetype=mimetype, 
        status=status, content=encode_func(content))

    
def _error(message):
    """
    Return an ajax error message for elfinder
    """
    return _ajax({'error': message})


def run_command(cmd, **data):
    """
    execute cmd if it is available in the driver
    """
    # pick the driver function from commands dictionary
    driver_func = getattr(driver, driver.commands[cmd])
    # driver_func accept only args and defaults
    args, _, _, defaults = inspect.getargspec(driver_func)
    # index of args with defaults
    index = len(args) - len(defaults or [])
    kwargs = {}
    for arg in args:
        if arg is 'self':
            continue
        if arg in data and data[arg]:
            kwargs[arg] = data[arg]
            continue
        # means mandatory argument and no default value present
        if args.index(arg) < index:
           raise Exception(
               'mandatory argument %s missing in command %s' % (arg, cmd))
    # call the driver function with parameters of the request
    content = driver_func(**kwargs)
    if 'init' in data:
        content.update(params.INIT_PARAMS)
    return content


@login_required
def index(request, root, template_name='elfinder/admin_finder.html'):
    context = {
        'title': _('File Manager'),
        'contextmenu': params.CONTEXT_MENU,
        'uioptions': params.UI_OPTIONS,
        'root': root
    }
    return render(request, template_name, context)


def connector(request, root):
    data_src = request.POST or request.GET
    # fill the data dict, needed to execute the command
    data = {
        'user': request.user,
        'root': root,
        'files': request.FILES,
    }
    # Copy allowed parameters from the given request's GET to self.data
    for field in params.ALLOWED_HTTP_PARAMS:
        if field in data_src:
            if field == "targets[]":
                data['targets'] = data_src.getlist(field)
            else:
                data[field] = data_src[field]
    if not 'cmd' in data:
        return _error('no cmd paramater found in the request')
    # check if 'cmd' is available in the driver and run it
    cmd = data.pop('cmd')
    if not cmd in driver.commands:
        return _error('command %s not available!' % cmd)
    try:
        content = run_command(cmd, **data)
    except Exception as e:
        return _error(e.message)
    # special commands (i.e. file) not return a dict to submit by ajax
    # so return the content from driver as it comes from the run_command
    if not isinstance(content, dict):
        return content
    return _ajax(content)


driver = getattr(settings, 'FINDER_DRIVER', FinderDriver())
