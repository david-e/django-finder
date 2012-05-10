from django.db import models
from django.utils.translation import ugettext as _

from model_utils.fields import AutoCreatedField, AutoLastModifiedField


class INode(models.Model):
    name = models.CharField(_('name'), max_length=256)
    owner = models.ForeignKey('auth.user',
        related_name='%(class)s_list',
        verbose_name=_('owner')
    )
    created = AutoCreatedField(_('created'))
    modified = AutoLastModifiedField(_('modified'))

    class Meta:
        abstract = True
        ordering = ['name']
        verbose_name = _('INode')
        verbose_name_plural = _('INodes')
        permissions = (
            ('can_read',  'Can read'),
            ('can_write', 'Can write'),
            ('can_exec',  'Can execute'),
        )
    
    def __unicode__(self):
        return self.name
