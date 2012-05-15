from django.contrib.auth.models import Permission, User
from django.db import models
from django.utils.translation import ugettext as _

from mptt.models import MPTTModel, MPTTModelBase, TreeForeignKey

import hashlib
from model_utils.fields import AutoCreatedField, AutoLastModifiedField
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
                    # if not a user
                    if not hasattr(user, 'has_perm'):
                        return False
                    return user.has_perm(permission, cls)
                setattr(cls, 'has_%s_permission' % perm, func) 


class INodeBase(MPTTModelBase):

    def __new__(cls, name, bases, attrs):
        inode_meta = attrs.pop('INodeMeta', None)
        new_class = super(INodeBase, cls).__new__(cls, name, bases, attrs)
        new_class.add_to_class('_inode_meta', INodeOptions(inode_meta))
        return new_class


class INode(MPTTModel):
    """
    Basic inode structure. This is used as base for directory and files classes.
    This class inherited from MPTModel, so dicrectory can use TreeForeignKey,
    while file (and file-subclasses) uses the standard models.Model facility.
    """
    PERMISSIONS = ('read', 'write', 'execute', 'remove', 'add')
    
    __metaclass__ = INodeBase
    
    name = models.CharField(_('name'), max_length=256)
    owner = models.ForeignKey('auth.user',
        related_name='%(class)s_list',
        verbose_name=_('owner')
    )
    created = AutoCreatedField(_('created'))
    modified = AutoLastModifiedField(_('modified'))
    
    class Meta:
        abstract = True
        verbose_name = _('INode')
        verbose_name_plural = _('INodes')
        ordering = ['name']
    
    def __unicode__(self):
        return self.name

    def __get_path__(self):
        path = ''
        def join(*args):
            p, separator = '', '/'
            for arg in args:
                if arg:
                    p += separator + arg
            return p
        while self.parent:
            path = join(self.parent.name, path)
        return join(path, self.name)
    path = property(__get_path__)
    
    def has_perm(self, perm, user):
        perm_function = 'has_%s_permission' % perm
        if hasattr(self, perm_function):
            return getattr(self, perm_function)(user)
        return False


class DirectoryNode(INode):
    """
    Directory base class.
    """    
    parent = TreeForeignKey('self', null=True, blank=True,
                               related_name='children_dirs',
                               verbose_name=_('parent node'))
    
    class Meta:
        verbose_name = _('Directory')
        verbose_name_plural = _('Directories')

    class INodeMeta:
        base_permissions = True

    @property
    def total_size(self):
        s = 0
        # size from all subdirectories
        for obj in self.children_dirs.all():
            s += obj.size
        # size of files in this directory
        for obj in self.children_files.all():
            s += obj.size
        return s

    @property
    def size(self):
        return 0
    

class FileNode(INode):
    """
    Base file node
    """
    parent = TreeForeignKey('DirectoryNode', null=True, blank=True,
                               related_name='children_files',
                               verbose_name=_('parent node'))
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


class ImageNode(FileNode):
    """
    Image file
    """
    width = models.IntegerField(_('width'), blank=True, null=True)
    height = models.IntegerField(_('height'), blank=True, null=True)

    class Meta:
        verbose_name = _('Image')
        verbose_name_plural = _('Images')