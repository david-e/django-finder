import mimetypes

from django.contrib.auth.models import Permission, User
from django.db import models
from django.utils.translation import ugettext as _

from model_utils.fields import AutoCreatedField, AutoLastModifiedField, Choices
from model_utils.managers import InheritanceManager

from elfinder.utils import get_path_for_upload


class INodeOptions(object):
    DEFAULT_NAMES = ('base_permissions', 'mimetypes')

    def __init__(self, meta):
        self.base_permissions = False
        self.mimetypes = [None]
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


class INodeManager(InheritanceManager):

    def get_hash(self, target_hash):
        """
        In this implementation hash is the inode primary key,
        but this method hides the magic.
        """
        return self.get_query_set().get(pk=target_hash)


class INode(models.Model):
    """
    Basic inode structure. This is used as base for directory and files classes
    """
    __metaclass__ = INodeBase

    PERMISSIONS = ('read', 'write', 'execute', 'remove', 'add')
    TYPES = Choices(('file', _('file')), ('folder', _('folder')))
    ROOT = {'PK': 1, 'HASH': 1}

    name = models.CharField(_('name'), max_length=256)
    itype = models.CharField(_('type'), max_length=10, null=True,
                             choices=TYPES)
    parent = models.ForeignKey('self', null=True, blank=True,
                            related_name='children',
                            verbose_name=_('parent node'),
                            limit_choices_to={
                                'itype': TYPES.folder
                            },
                            default=ROOT['PK']
    )
    owner = models.ForeignKey('auth.user', related_name='%(class)s_list',
                              verbose_name=_('owner'))
    created = AutoCreatedField(_('created'))
    modified = AutoLastModifiedField(_('modified'))

    objects = INodeManager()
    
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
        return ''

    @property
    def size(self):
        return 0
    
    @property
    def path(self):
        p = self.name
        while self.parent:
            p = '/'.join([self.parent.name, p])
        return '/%s' % p

    @property
    def mimetype(self):
        return self._inode_meta.mimetypes[0]

    def info(self, user=None):
        return {
            'name' : self.name,
            'hash' : self.hash,
            'phash': self.phash,
            'mime' : self.mimetype,
            'size' : self.size,
            'read' : self.has_perm('read', user),
            'write': self.has_perm('write', user),
            'rm'   : self.has_perm('remove', user)
        }

    def list_folders(self):
        return INode.objects.filter(itype=INode.folder)

    def list_files(self):
        return INode.objects.filter(itype=INode.file)

    def get_ancestors(self, include_self=False):
        ancestors = []
        curr_node = self if include_self else self.parent
        while curr_node:
            ancestors.insert(0, curr_node) # insert at the beggining
            curr_node = curr_node.parent
        return ancestors

    def get_siblings(self,):
        siblings = []
        if self.parent:
            siblings = INode.objects.filter(parent=self.parent)
        return siblings

class FolderNode(INode):
    """
    Base folder node
    """
    TYPE = INode.TYPES.folder

    objects = INodeManager()

    class Meta:
        verbose_name = _('Folder')
        verbose_name_plural = _('Folders')

    class INodeMeta:
        base_permissions = True
        mimetypes = ['directory']
    
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

    def info(self, user):
        info = super(FolderNode, self).info(user)
        info['dirs'] = int(
            self.children.filter(itype=INode.TYPES.folder).count() > 0)
        return info


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
        mimetypes = ['text/plain']

    @property
    def size(self):
        return self.data.size

    @property
    def base_path(self):
        p = self.path
        # all the string until last '/'
        return p[:p.rfind('/')]

    @property
    def mimetype(self):
        mimetypes.guess_type(self.data.url)[0] # first element of the tuple


class ImageNode(FileNode):
    width = models.IntegerField(_('width'))
    height = models.IntegerField(_('height'))

    class Meta:
        verbose_name = _('Image')
        verbose_name_plural = _('Images')

    class INodeMeta:
        mimetypes = ['image/png', 'image/jpeg', 'image/gif']
