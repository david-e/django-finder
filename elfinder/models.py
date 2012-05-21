import mimetypes
import os
import time
import Image
from django.contrib.auth.models import Permission, User
from django.conf import settings
from django.db import models
from django.utils.translation import ugettext as _
from model_utils.fields import AutoCreatedField, AutoLastModifiedField, Choices
from model_utils.managers import InheritanceManager
from elfinder import utils as elutils

import logging


class INodeOptions(object):
    DEFAULT_NAMES = ('base_permissions', 'mimetypes')

    def __init__(self, meta):
        self.base_permissions = False
        self.mimetypes = []
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
        for mimetype in self.mimetypes:
            INode.MIMETYPES[mimetype] = cls

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
        return self.get_subclass(pk=target_hash)


class INode(models.Model):
    """
    Basic inode structure. This is used as base for directory and files classes
    """
    __metaclass__ = INodeBase

    """
    add     - is the permission to add folders or files to a target folder
    remove  - is the permission to remove a file or a folder
    read    - is the permission to read the content of a file or a folder
    write   - is the permission to rename files or folders
    execute - is the permission to pass through a folder (unused at the moment)
    """
    PERMISSIONS = ('read', 'write', 'execute', 'remove', 'add')
    TYPES = Choices(('file', _('file')), ('folder', _('folder')))
    ROOT = {'PK': 1, 'HASH': 1}

    # dictionary filled at runtime with 'mimetype': ModelClass that handle
    # the upload
    MIMETYPES = {}

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
    mime = models.CharField(max_length=30, blank=True, null=True)
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

    def to_timestamp(self, datetime):
        return time.mktime(datetime.timetuple())

    def info(self, user=None):
        return {
            'name'  : self.name,
            'hash'  : self.hash,
            'phash' : self.phash,
            'mime'  : self.mime,
            'size'  : self.size,
            'read'  : self.has_perm('read', user),
            'write' : self.has_perm('write', user),
            'rm'    : self.has_perm('remove', user),
            'ts'    : self.to_timestamp(self.modified),
            'locked': int(self.pk == self.ROOT['PK']),
        }

    def all_folders(self):
        return INode.objects.filter(itype=INode.folder)

    def all_files(self):
        return INode.objects.filter(itype=INode.file)

    def get_ancestors(self, include_self=False):
        ancestors = []
        curr_node = self if include_self else self.parent
        while curr_node:
            ancestors.insert(0, curr_node) # insert at the beggining
            curr_node = curr_node.parent
        return ancestors

    def get_siblings(self):
        siblings = []
        if self.parent:
            siblings = INode.objects.filter(parent=self.parent)
        return siblings

    def clone(self, **kwargs):
        initial = {}
        for f in self._meta.fields:
            if (isinstance(f, models.AutoField) or
                    isinstance(f, models.OneToOneField)):
                continue
            key = f.name
            if isinstance(f, models.FileField):
                base = getattr(getattr(self, f.name), 'name')
            else:
                base = getattr(self, f.name)
            initial[key] = kwargs.get(key, base)
        return self.__class__.objects.create(**initial)


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

    def __init__(self, *args, **kwargs):
        super(FolderNode, self).__init__(*args, **kwargs)
        self.mime = 'directory'

    @property
    def total_size(self):
        s = 0
        # size from all subdirectories
        for item in self.children.select_subclasses():
            s += item.total_size
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
                            upload_to=elutils.get_path_for_upload)

    class Meta:
        verbose_name = _('File')
        verbose_name_plural = _('Files')

    class INodeMeta:
        base_permissions = True
        mimetypes = ['application/octet-stream']


    def __init__(self, *args, **kwargs):
        super(FileNode, self).__init__(*args, **kwargs)
        if hasattr(self.data, 'name'):
            self.mime = mimetypes.guess_type(self.data.name)[0]

    @property
    def size(self):
        return self.data.size

    @property
    def total_size(self):
        return self.size

    @property
    def base_path(self):
        p = self.path
        # all the string until last '/'
        return p[:p.rfind('/')]

    @property
    def mimetype(self):
        mimetypes.guess_type(self.data.url)[0] # first element of the tuple

    def info(self, user):
        info = super(FileNode, self).info(user)
        info['mime'] = self.mime
        return info


class ImageNode(FileNode):
    # thumb contain the filename of the thumbnails
    thumb = models.CharField(_('thumbnail'), max_length=256,
                             blank=True, null=True)
    width = models.IntegerField(_('width'), blank=True, null=True)
    height = models.IntegerField(_('height'), blank=True, null=True)

    def save(self, *args, **kwargs):
        # analyze image to find characteristics when created
        if not self.pk and not os.path.exists(self.data.name):
            try:
                image = Image.open(self.data)
                self.width, self.height = image.size
                image.thumbnail((128, 128))
                thumbname = elutils.get_path_for_upload(
                    self, '128x128_%s'% self.data, rel_path='thumbs')
                image.save(thumbname, 'JPEG')
                # get a valid url starting from a file system path
                self.thumb = elutils.get_url(thumbname)
            except Exception as e:
                logging.error(e.message)
                logging.error('%s is not a valid image' % self.data.name)
        super(ImageNode, self).save(*args, **kwargs)

    class Meta:
        verbose_name = _('Image')
        verbose_name_plural = _('Images')

    class INodeMeta:
        mimetypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif']

    def info(self, user=None):
        inf = super(ImageNode, self).info(user=user)
        if self.width and self.height:
            inf['dim'] = '%sx%s' % (self.width, self.height)
        inf['tmb'] = self.thumb
        return inf
        
