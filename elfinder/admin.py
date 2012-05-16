from django.contrib import admin

from elfinder import models

admin.site.register(models.FileNode)
admin.site.register(models.FolderNode)