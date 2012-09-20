from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def index(request, template_name='elfinder/admin_finder.html'):
    context = {
        'title': 'File Manager',
    }
    return render(request, template_name, context)


def connector_view(request, coll_id):
    return HttpResponse()

