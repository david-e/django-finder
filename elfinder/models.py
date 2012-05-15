from django.contrib.auth.models import Permission, User
from django.db import models
from django.utils.translation import ugettext as _

from model_utils.fields import AutoCreatedField, AutoLastModifiedField, Choices

from elfinder.utils import get_path_for_upload


class INodeOptions(object):
    DEFAULT_NAMES = ('base_permissions',)

    def __init__(self, meta):
        self.base_permissions = False
        self.meta = meta

    def contribute_to_class(self, cls, name):
        cls._inode_meta = self
        if self.meta:
            meta_attrs = self.meta.__dict__.copy()
            for attr_name in self.DEFAULT_NAMES:
                if attr_name in meta_attrs:
                    setattr(self, attr_name, meta_attrs.pop(attr_name))
        del self.meta
        # add basic file/folder permissions functions
        if self.base_permissions:
            for perm in cls.PERMISSIONS:
                def func(self, user):
                    permission = Permission.objects.get(
                        codename='%s_%s' % (perm,
                                            cls._meta.verbose_name.lower())
                    )
                    # superuser can everything
                    if isinstance(user, User):
                        return (user.is_superuser or
                                user.has_perm(permission, cls))
                    return False
                setattr(cls, 'has_%s_permission' % perm, func) 


class INodeBase(models.base.ModelBase):

    def __new__(cls, name, bases, attrs):
        inode_meta = attrs.pop('INodeMeta', None)
        new_class = super(INodeBase, cls).__new__(cls, name, bases, attrs)
        new_class.add_to_class('_inode_meta', INodeOptions(inode_meta))
        return new_class


class INode(models.Model):
    """
    Basic inode structure. This is used as base for directory and files classes
    """
    __metaclass__ = INodeBase

    PERMISSIONS = ('read', 'write', 'execute', 'remove', 'add')
    TYPES = Choices(('file', _('file')), ('folder', _('folder')))

    name = models.CharField(_('name'), max_length=256)
    itype = models.CharField(_('type'), max_length=10, null=True,
                             choices=TYPES)
    parent = models.ForeignKey('self', null=True, blank=True,
                            related_name='children',
                            verbose_name=_('parent node'),
                            limit_choices_to={
                                'inode_type': TYPES.folder
                            }
    )
    owner = models.ForeignKey('auth.user', related_name='%(class)s_list',
                              verbose_name=_('owner'))
    created = AutoCreatedField(_('created'))
    modified = AutoLastModifiedField(_('modified'))
    
    class Meta:
        verbose_name = _('INode')
        verbose_name_plural = _('INodes')
        unique_together = ('name', 'parent')
        ordering = ['name']
    
    def __unicode__(self):
        return self.name
   
    def has_perm(self, perm, user):
        perm_function = 'has_%s_permission' % perm
        if hasattr(self, perm_function):
            return getattr(self, perm_function)(user)
        # superuser can everything
        if isinstance(user, User):
            return user.is_superuser
        return False

    def _set_node(node):
        self._node = node
        node.save()
        self._node_id = node.id
    
    def __init__(self, *args, **kwargs):
        super(INode, self).__init__(*args, **kwargs)
        # set type of the inode
        if hasattr(self, 'TYPE'):
            self.itype = self.TYPE

    def save(self, *args, **kwargs):
        self.full_clean()
        return super(INode, self).save(*args, **kwargs)
    
    @property
    def hash(self):
        return self.pk

    @property
    def phash(self):
        if self.parent:
            return self.parent.pk
        return None

    @property
    def size(self):
        return 0
    
    @property
    def path(self):
        p = self.name
        while self.parent:
            p = '/'.join([self.parent.name, p])
        return '/%s' % p


class FolderNode(INode):
    """
    Base folder node
    """
    TYPE = INode.TYPES.folder

    class Meta:
        verbose_name = _('Folder')
        verbose_name_plural = _('Folders')

    class INodeMeta:
        base_permissions = True
    
    @property
    def total_size(self):
        s = 0
        # size from all subdirectories
        children = self.children.all()
        for obj in children.filter(inode_type=TYPES.folder):
            s += obj.size
        # size of files in this directory
        for obj in children.filter(inode_type=TYPES.file):
            s += obj.size
        return s


class FileNode(INode):
    """
    Base file node
    """
    TYPE = INode.TYPES.file
    
    data = models.FileField(_('File'), max_length=256,
                            upload_to=get_path_for_upload)

    class Meta:
        verbose_name = _('File')
        verbose_name_plural = _('Files')

    class INodeMeta:
        base_permissions = True

    @property
    def size(self):
        return self.data.size

    @property
    def base_path(self):
        p = self.path
        # all the string until last '/'
        return p[:p.rfind('/')]


class ImageNode(FileNode):
    width = models.IntegerField(_('width'))
    height = models.IntegerField(_('height'))

    class Meta:
        verbose_name = _('Image')
        verbose_name_plural = _('Images')
