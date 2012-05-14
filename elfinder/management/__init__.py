from django.contrib.auth.models import Permission
from django.db.models import signals
from elfinder import models

INODE_BASE_CLASSES = [
    models.FileNode,
    models.DirectoryNode,
]

def elfinder_create_permissions(verbosity, **kwargs):
    from django.contrib.contenttypes.models import ContentType
    objs = []
    for klass in INODE_BASE_CLASSES:
        ctype = ContentType.objects.get_for_model(klass)
        # create a tuple of all existing permissions
        all_perms = set(Permission.objects.filter(
            content_type=ctype,
        ).values_list(
            "content_type", "codename"
        ))
        for perm_name in models.INode.PERMISSIONS:
            # same string used in has_$(perm_name)_permission of the INode class
            klass_name = klass._meta.verbose_name.lower()
            codename = '%s_%s' % (perm_name, klass_name)
            # skip if this permission is already created
            if (ctype.pk, codename) in all_perms:
                continue
            objs.append(
                Permission(
                    codename = codename,
                    name = 'Can %s %s' % (perm_name, klass_name),
                    content_type = ctype
                )
            )
    Permission.objects.bulk_create(objs)
    if verbosity >= 2:
        for obj in objs:
            print "Adding permission '%s'" % obj

signals.post_syncdb.connect(elfinder_create_permissions,
    dispatch_uid = "elfinder.create_permissions")