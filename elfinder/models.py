from django.db import models
from django.utils.translation import ugettext as _

from mptt.models import MPTTModel, TreeForeignKey

from model_utils.fields import AutoCreatedField, AutoLastModifiedField

from elfinder.utils import get_path_for_upload


class INode(MPTTModel):
    """
    Basic inode structure. This is used as base for directory and files classes.
    This class inherited from MPTModel, so dicrectory can use TreeForeignKey,
    while file (and file-subclasses) uses the standard models.Model facility.
    """
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

    def _get_path(self):
        path =  '/' + self.name
        while hasattr(self, 'parent'):
            path = '/' + self.parent.name + path
        return path
    path = property(_get_path)


class DirectoryNode(INode):
    """
    Directory base class.
    """
    parent = TreeForeignKey('self', null=True, blank=True,
                               related_name='dirs',
                               verbose_name=_('parent node'))

    class Meta:
        verbose_name = _('Directory')
        verbose_name_plural = _('Directories')
        permissions = (
            ('can_read',  'Can read'),
            ('can_write', 'Can write'),
            ('can_exec',  'Can execute'),
        )
    

class FileNode(INode):
    """
    Base file node
    """
    parent = TreeForeignKey('DirectoryNode', null=True, blank=True,
                               related_name='files',
                               verbose_name=_('parent node'))
    data = models.FileField(_('File'), max_length=256,
                            upload_to=get_path_for_upload)

    class Meta:
        verbose_name = _('File')
        verbose_name_plural = _('Files')
        permissions = (
            ('can_read',  'Can read'),
            ('can_write', 'Can write'),
            ('can_exec',  'Can execute'),
        )


class ImageNode(FileNode):
    """
    Image file
    """
    width = models.IntegerField(_('width'), blank=True, null=True)
    height = models.IntegerField(_('height'), blank=True, null=True)

    class Meta:
        verbose_name = _('Image')
        verbose_name_plural = _('Images')