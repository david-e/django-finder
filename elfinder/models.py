from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.core.exceptions import FieldError
from django.db import models
from django.utils.translation import ugettext_lazy as _

from mptt.models import MPTTModel, TreeForeignKey, TreeManager

import Image as PILimage
import os
import time

from elfinder import utils

"""
 MIMETYPES is a dictionary filled at runtime. The keys are the mimetypes, the 
 values are the classes that handle them. To manage a new mimetype create
a class that inherited from BaseFile or File and create a mimetypes list 
 attribute in the FileMeta of a new model.
 """
MIMETYPES = {}
    

class FileOptions(object):
    """
    Manage permissions and mimetypes facilities.
    """
    DEFAULT_NAMES = ('base_permissions', 'mimetypes')

    def __init__(self, meta):
        self.base_permissions = False
        self.mimetypes = []
        self.meta = meta

    def contribute_to_class(self, cls, name):
        cls._file_meta = self
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
            MIMETYPES[mimetype] = cls


class INodeManager(TreeManager):

    def get_hash(self, target_hash):
        """
        In this implementation hash is the inode primary key,
        but this method hides the magic.
        """
        return self.get(pk=target_hash).get_rel_type()


class INode(MPTTModel):
    """
    This class rapresents the inode structure in the file system.
    Parent could be only of inode_type folder.
    This class is in relation with the Folder model class and the File 
    abstract model class.
    """
    parent = TreeForeignKey('self', null=True, blank=True,
                            related_name='children')
    # related_type contains Model._meta.module_name to retrieve
    # folder or file instance starting from an inode instance
    related_type = models.CharField(_('Type'), max_length=64)
    # null owner means everybody has permissions of everything
    owner = models.ForeignKey('auth.user', verbose_name=_('Owner'),
                              blank=True, null=True)
    created = utils.AutoCreatedField(_('Created'))
    modified = utils.AutoLastModifiedField(_('Modified'))

    objects = INodeManager()

    def get_rel_type(self):
        obj = self
        for klass in self.related_type.split('.'):
                obj = getattr(obj, klass)
        return obj


class FileModelBase(models.base.ModelBase):

    def __new__(cls, name, bases, attrs):
        file_meta = attrs.pop('FileMeta', None)
        new_class = super(FileModelBase, cls).__new__(cls, name, bases, attrs)
        new_class.add_to_class('_file_meta', FileOptions(file_meta))
        return new_class


class FileManager(models.Manager):

    def _correct_kwargs(self, **kwargs):
        k = kwargs.copy()
        parent = k.pop('parent', None)
        if parent:
            p_inode = getattr(parent, 'inode', None)
            k['inode__parent'] = p_inode
        owner = k.pop('owner', None)
        if owner:
            kwargs['inode_owner'] = owner
        return k

    def get(self, **kwargs):
        k = self._correct_kwargs(**kwargs)
        return super(FileManager, self).get(**k)

    def filter(self, **kwargs):
        k = self._correct_kwargs(**kwargs)
        return super(FileManager, self).filter(**k)

    def get_or_create(self, *args, **kwargs):
        try:
            folder = self.get(**kwargs)
            return folder, False
        except Folder.DoesNotExist:
            return self.create(*args, **kwargs), True
                  
        
class BaseFile(models.Model):
    """
    This mixin take advantage of the MPTTModel functionalities to provide
    methods for files and folder instances
    Permissions:
    add     - is the permission to add folders or files to a target folder
    remove  - is the permission to remove a file or a folder
    read    - is the permission to read the content of a file or a folder
    write   - is the permission to rename files or folders
    execute - is the permission to pass through a folder (unused at the moment)
    """    
    __metaclass__ = FileModelBase

    PERMISSIONS = ('read', 'write', 'execute', 'remove', 'add')
    
    name = models.CharField(_('Name'), max_length=256)

    objects = FileManager()
    
    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        parent = kwargs.pop('parent', None)
        if parent and not isinstance(parent, Folder):
            raise FieldError('Parent must be None or a Folder instance')
        owner = kwargs.pop('owner', None)
        super(BaseFile, self).__init__(*args, **kwargs)
        if not self.pk:
            self.inode = INode(
                parent=getattr(parent, 'inode', None),
                related_type=self._get_related_name(), 
                owner=owner
            )

    def __unicode__(self):
        return self.name

    def _get_related_name(self):
        """
        this method fill the inode related_type char field with the path to 
        retrieve the class linked to the specific inode.
        """
        cls = self.__class__
        rel_name = cls.__name__.lower()
        for base in cls.__bases__:
            if base == BaseFile:
                break
            rel_name = "%s.%s" % (base.__name__.lower(), rel_name)
        return rel_name
        
    def _get_inodes_type(self, inodes):
        return map(lambda i: i.get_rel_type(), inodes)

    def has_perm(self, perm, user):
        perm_function = 'has_%s_permission' % perm
        if hasattr(self, perm_function):
            return getattr(self, perm_function)(user)
        # superuser can everything
        if isinstance(user, User):
            return user.is_superuser
        return False
    
    def move(self, dst):
        self.inode.parent = dst.inode
        self.inode.save()

    def save(self, *args, **kwargs):
        # if related inode is not saved yet, save it and annotate the id
        if not self.inode_id:
            self.inode.save()
            self.inode_id = self.inode.id
        super(BaseFile, self).save(**kwargs)
        
    def delete(self, *args, **kwargs):
        super(BaseFile, self).delete(*args, **kwargs)
        # delete relative inode also
        self.inode.delete()

    def clone(self, parent, **kwargs):
        initial = {'parent': parent}
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
    
    def get_ancestors(self):
        ancestors = INode.get_ancestors(self.inode)
        return self._get_inodes_type(ancestors)

    def get_children(self):
        # inodes list of children
        children = INode.get_children(self.inode)
        return self._get_inodes_type(children)

    def get_siblings(self):
        siblings = INode.get_siblings(self.inode)
        return self._get_inodes_type(siblings)

    @property
    def parent(self):
        return getattr(self.inode.parent, 'folder', None)


class ElfinderMixin(object):
    """
    This mixin wraps all functionalities needed by the elfinder web gui to work.
    """
    @property
    def hash(self):
        return self.inode.pk

    @property
    def phash(self):
        return self.parent.hash if self.parent else ''

    @property
    def size(self):
        if hasattr(self, 'raw'):
            return self.raw.size
        return 0

    @property
    def total_size(self):
        return self.size

    @property
    def mimetype(self):
        return self._file_meta.mimetypes[0]
    
    @property
    def path(self):
        p = self.name
        while self.parent:
            p = '/'.join([self.parent.name, p])
        return '/%s' % p

    @property
    def modified(self):
        return self.inode.modified

    @property
    def created(self):
        return self.inode.created

    @property
    def owner(self):
        return self.inode.owner
        
    @property
    def timestamp(self):
        return time.mktime(self.modified.timetuple())

    def info(self, user=None):
        return {
            'name'  : self.name,
            'hash'  : self.hash,
            'phash' : self.phash,
            'mime'  : self.mimetype,
            'size'  : self.size,
            'read'  : self.has_perm('read', user),
            'write' : self.has_perm('write', user),
            'rm'    : self.has_perm('remove', user),
            'ts'    : self.timestamp,
            'locked': int(self.inode.parent is None)
        }
    

class Folder(BaseFile, ElfinderMixin):
    """
    This class has a onetoonefield with the Inode MTTPModel to mantain
    the relation between inodes and folder instances. When a folder is created 
    creates a new inode instance and link it with the choosen (from a form) 
    father folder.
    """    
    inode = models.OneToOneField('elfinder.inode')

    class Meta:
        verbose_name = _('Folder')
        verbose_name_plural = _('Folders')

    class FileMeta:
        mimetypes = ['directory']

    @property
    def total_size(self):
        s = 0
        # size from all subdirectories
        for item in self.get_children():
            s += item.total_size
        return s

    def info(self, user=None):
        i = super(Folder, self).info(user)
        i['dirs'] = Folder.objects.filter(parent=self).count()
        return i     


class File(BaseFile, ElfinderMixin):    
    inode = models.OneToOneField('elfinder.inode')
    raw = models.FileField(_('File data'), max_length=512, 
                            upload_to=utils.get_upload_path)
    
    class Meta:
        verbose_name = _('File')
        verbose_name_plural = _('Files')
        
    class FileMeta:
        mimetypes = ['application/octet-stream']

    def __init__(self, *args, **kwargs):
        super(File, self).__init__(*args, **kwargs)
        if not self.inode.parent:
            raise FieldError('File instance must have a Folder as parent')
        if not 'name' in kwargs and self.raw:
            kwargs['name'] = os.path.basename(self.raw.name)


class Image(File):
    """
    Image class
    """
    thumb = models.CharField(_('thumbnail'), max_length=256,
                             blank=True, null=True)
    width = models.IntegerField(_('width'), blank=True, null=True)
    height = models.IntegerField(_('height'), blank=True, null=True)

    class Meta:
        verbose_name = _('Image')
        verbose_name_plural = _('Images')

    class FileMeta:
        mimetypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif']

    def save(self, *args, **kwargs):
        # analyze image for thumbnail and resolution the first time
        if not self.pk:
            img = PILimage.open(self.raw)
            self.width, self.height = img.size
            img.thumbnail((128, 128))
            thumbname = os.path.join(settings.MEDIA_ROOT, 
                utils.get_upload_path(self, '128x128_%s' % self.raw, 
                rel_path='thumbs'))
            img.save(thumbname, 'JPEG')
            # get a valid url starting from a file system path
            self.thumb = utils.get_url(thumbname)
        super(Image, self).save(*args, **kwargs)

    def info(self, user=None):
        inf = super(Image, self).info(user=user)
        if self.width and self.height:
            inf['dim'] = '%sx%s' % (self.width, self.height)
        inf['tmb'] = self.thumb
        return inf
