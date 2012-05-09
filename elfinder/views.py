from django.template.response import TemplateResponse


def index(request, template_name='elfinder/base.html'):
    context = {
        'title': 'File Manager',
    }
    return TemplateResponse(request, template_name, context)


def connector_view(request, coll_id):
    return HttpResponse()