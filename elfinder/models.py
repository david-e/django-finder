from django.db import models
from django.utils.translation import ugettext_lazy as _

from mptt.models import MPTTModel, TreeForeignKey

import utils


class INode(MPTTModel):
    """
    This class rapresents the inode structure in the file system.
    Parent could be only of inode_type folder.
    This class is in relation with the Folder model class and the File 
    abstract model class.
    """
    TYPES = utils.Choices(('folder', _('Folder')), ('file', _('File')))
    
    parent = TreeForeignKey('self', null=True, blank=True,
                            related_name='children',
                            limit_choices_to= { 'type': 'folder' })
    itype = models.CharField(_('Type'), default=TYPES.folder, max_length=16,
                                  choices=TYPES)
    owner = models.ForeignKey('auth.user', verbose_name=_('Owner'))
    created = utils.AutoCreatedField(_('Created'))
    modified = utils.AutoLastModifiedField(_('Modified'))

    
class Folder(models.Model):
    """
    This class has a onetoonefield with the Inode MTTPModel to mantain
    the relation between inodes and folder instances. When a folder is created 
    creates a new inode instance and link it with the choosen (from a form) 
    father folder.
    """
    name = models.CharField(_('Name'), max_length=64)
    inode = models.OneToOneField('elfinder.inode', related_name='folder')

    class Meta:
        verbose_name = _('Folder')
        verbose_name_plural = _('Folders')

    def save(self, owner, parent=None, **kwargs):
        # the first save create the related inode
        if not self.pk:
            self.inode = INode.objects.create(
                parent=parent.inode, itype=INode.TYPES.folder, owner=owne        return super(Folder, self).save(**kwargs)

        
class File(models.Model):
    name = models.CharField(_('Name'), max_length=256)
    inode = models.OneToOneField('elfinder.inode', related_name='file')
    raw = models.FileField(_('File data'), max_length=512, 
                            upload_to=utils.get_upload_path)
    
    class Meta:
        verbose_name = _('File')
        verbose_name_plural = _('Files')
        
    def save(self, owner, parent, **kwargs):
        # the first save create the related inode
        if not self.pk:
            if not self.name:
                self.name = self.raw.name
            self.inode = INode.objects.create(
                parent=parent.inode, itype=INode.TYPES.file, owner=owner)
        return super(File, self).save(**kwargs)
