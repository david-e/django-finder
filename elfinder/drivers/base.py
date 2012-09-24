from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect

import logging
import mimetypes

from elfinder import models, params, utils


class BaseDriver(object):
    commands = []  # list containing all available commands
    
    def __init__(self, *args, **kwargs):
        pass

    def info(self, target, user=None):
        """
        Returns a dict containing information about the target directory
        or file. This data is used in response to 'open' commands to
        populates the 'cwd' response var.
        :param target: The hash of the directory for which we want info.
        If this is '', return information about the root directory.
        :returns: dict -- A dict describing the directory.
        """
        raise NotImplementedError

    def open(self, target_hash=None,
             user=None, ancestors=False, siblings=False):
        """
        Gets a list of dicts describing children/ancestors/siblings of the
        target.
        :param target: The hash of the directory the tree starts from.
        :param ancestors: Include ancestors of the target.
        :param siblings: Include siblings of the target.
        :param children: Include children of the target.
        :returns: list -- a list of dicts describing directories.
        """
        raise NotImplementedError

    def read_file_view(self, request, hash, user=None):
        """
        Django view function, used to display files in response to the
        'file' command.
        :param request: The original HTTP request.
        :param hash: The hash of the target file.
        :returns: dict -- a dict describing the new directory.
        """
        raise NotImplementedError

    def mkdir(self, name, target, user=None):
        """
        Creates a directory.
        :param name: The name of the new directory.
        :param target: The hash of the parent directory.
        :returns: dict -- a dict describing the new directory.
        """
        raise NotImplementedError

    def mkfile(self, name, target, user=None):
        """
        Creates a file.
        :param name: The name of the new file.
        :param target: The hash of the parent directory.
        :returns: dict -- a dict describing the new file.
        """
        raise NotImplementedError

    def rename(self, name, target, user=None):
        """
        Renames a file or directory.
        :param name: The new name of the file/directory.
        :param target: The hash of the target file/directory.
        :returns: dict -- a dict describing which objects were added and
        removed.
        """
        raise NotImplementedError

    def list(self, target, user=None):
        """
        Lists the contents of a directory.
        :param target: The hash of the target directory.
        :returns: list -- a list containing the names of files/directories
        in this directory.
        """
        raise NotImplementedError

    def paste(self, targets, source, dest, cut, user=None):
        """
        Moves/copies target files/directories from source to dest.
            If a file with the same name already exists in the dest directory
        it should be overwritten (the client asks the user to confirm this
        before sending the request).
        :param targets: A list of hashes of files/dirs to move/copy.
        :param source: The current parent of the targets.
        :param dest: The new parent of the targets.
        :param cut: Boolean. If true, move the targets. If false, copy the
        targets.
        :returns: dict -- a dict describing which targets were moved/copied.
        """
        raise NotImplementedError

    def remove(self, target, user=None):
        """
        Deletes the target files/directories.
        The 'rm' command takes a list of targets - this function is called
        for each target, so should only delete one file/directory.

        :param targets: A list of hashes of files/dirs to delete.
        :returns: string -- the hash of the file/dir that was deleted.
        """
        raise NotImplementedError

    def upload(self, files, parent, user=None):
        """
        Uploads one or more files in to the parent directory.
        :param files: A list of uploaded file objects, as described here:
        https://docs.djangoproject.com/en/dev/topics/http/file-uploads/
        :param parent: The hash of the directory in which to create the
        new files.
        """
        raise NotImplementedError


class FinderDriver(BaseDriver):
    # this dict contain the relation between the command requested from elfinder
    # and the function of the driver that perform the command
    commands = {
        'open': 'open',
        'tree': 'tree',
        'list': 'list',
        'mkdir': 'mkdir',
        'rename': 'rename',
        'rm': 'remove',
        'paste': 'paste',
        'parents': 'parents',
        'upload': 'upload',
        'size': 'size',
        'file': 'file',
        'search': 'search',
    }

    def __init__(self, inode_model = models.INode,
                 folder_model=models.Folder, file_model=models.File):
        self.inode_model = inode_model
        self.folder_model = folder_model
        self.file_model = file_model

    def _get_inode(self, target_hash):
        """
        Return the inode cast to subclasses
        """
        return self.inode_model.objects.get_hash(target_hash)

    def _inode_info(self, inode, root, user, perm='read'):
        """
        Append inode informations if perm is available for the user.
        inode and root must be BaseFile instances.
        """            
        if not inode.has_perm(perm, user):
            return None
        info = inode.info(user)
        # if this is considered as root ensure that phash is none
        if inode == root:
            info['phash'] = ''
        return info
    
    def _get_tree(self, root, target, user=None, tree=None, include_self=True):
        """
        this function creates a list with all the inodes that user has 
        permission to read. If tree is True the list must contains also all
        ancestors and siblings inodes.
        """
        curr_node = self._get_inode(target)
        root_node = self._get_inode(root)

        def get_info(item):
            return self._inode_info(item, root_node, user)

        data = map(get_info, curr_node.get_children())
        if include_self:
            data.append(get_info(curr_node))
        if tree:
            data.extend(map(get_info, curr_node.get_ancestors()))
            data.extend(map(get_info, curr_node.get_siblings()))
        return data

    def cwd(self, root, target, user=None):
        node = self._get_inode(target)
        curr = node.info(user)
        if target == root:
            curr['phash'] = ''
        return curr

    def parents(self, root, target, user=None):
        tree = self._get_tree(root, target, tree=True, user=user)
        return {'parents': tree}
    
    def tree(self, root, target, user=None):
        """
        Return 
        """
        tree = self._get_tree(root, target, user=user)
        return {'tree': tree}

    def open(self, root, target=None, tree=None, user=None):
        """
        Handles the open command
        """
        target = target or root
        return {
            'files': self._get_tree(root, target, user=user, tree=tree),
            'cwd': self.cwd(root, target, user)
        }
        
    def list(self, target, user=None, root=None):
        """
        Returns a list of files/directories in the target directory.
        """
        tree = self._get_tree(root, target, user=user)
        inode_list = [inode['name'] for inode in tree]
        return {'list': inode_list}

    def mkdir(self, name, target, user=None):
        par_dir = self._get_inode(target)
        if not par_dir.has_perm('add', user):
            raise PermissionDenied('You do not have permission \
                                   to create folder in %s' % par_dir.name)
        new_dir, created = self.folder_model.objects.get_or_create(
            name = name,
            parent = par_dir,
            owner = user,
        )
        return {'added': [new_dir.info(user)]}

    def rename(self,  name, target, user=None):
        inode = self._get_inode(target)
        if not inode.has_perm('write', user):
            raise PermissionDenied('You do not have permission \
                                   to rename %s' % inode.name)
        inode.name = name
        inode.save()
        return {
            'added': [inode.info(user)],
                'removed': [target]
        }

    def remove(self, targets, user=None):
        removed = []
        for target in targets:
            inode = self._get_inode(target)
            if not inode.has_perm('remove', user):
                raise PermissionDenied('You do not have permission \
                                   to remove %s' % inode.name)
            inode.delete()
            removed.append(target)
        return {
            'removed': removed
        }

    def paste(self, targets, src, dst, cut, user=None):
        removed, added = [], []
        src_dir = self._get_inode(src)
        dst_dir = self._get_inode(dst)
        # check user permission on destination folder
        if not dst_dir.has_perm('add', user):
            raise PermissionDenied('You do not have permission \
                                    to add anything in %s' % dst_dir.name)
        for target in targets:
            inode = self._get_inode(target)
            # check read permission on target inode
            if not inode.has_perm('read', user):
                raise PermissionDenied('You do not have permission \
                                        to read %s' % inode.name)
            # check if inode.name is not already present in destination folder
            if self.folder_model.objects.filter(
                    name=inode.name, parent=inode.parent).count():
                raise Exception('%s is already present in %s' % (inode.name,
                                                             dst_dir.name))
            new_inode = inode.clone(parent=dst_dir)
            added.append(new_inode.info(user))
            if cut == '1':
                if not inode.has_perm('remove', user):
                     raise PermissionDenied('You do not have permission \
                                            to remove %s' % inode.name)
                inode.delete()
                removed.append(target)
        return {'added': added, 'removed': removed}

    def size(self, targets, user=None):
        size = 0
        for target in targets:
            inode = self._get_inode(target)
            size += inode.total_size
        return {'size': size}

    def upload(self, target, files, user=None):
        parent = self._get_inode(target)
        added = []
        if not parent.has_perm('add', user):
            raise PermissionDenied('You do not have permission \
                                    to add anything in %s' % parent.name)
        for key, data in files.items():
            # guess the type from the filename and get the class that handles it
            filename = data.name
            if self.file_model.objects.filter(name=filename,
                    parent=parent).count() > 0:
                raise Exception('File %s already exists here!' % filename)
            # guess_type return a tuple (mimetype, extensions)
            mimetype = mimetypes.guess_type(filename)[0]
            FileKlass = models.MIMETYPES.get(mimetype,
                                                       self.file_model)
            obj = FileKlass(
                name=filename,
                parent=parent,
                owner=user,
                raw=data
            )
            obj.save()
            added.append(obj.info(user))
        return {'added': added}

    def file(self, target, user=None):
        inode = self._get_inode(target)
        if not inode.has_perm('read', user):
            raise PermissionDenied('You do not have permission \
                                    to read anything in %s' % inode.name)
        url = inode.raw.url
        return HttpResponseRedirect(url)

    def search(self, q, user=None, root=None):
        data = self._get_tree(root, root, user)
        files = []
        for item in data:
            if q in item['name']:
                files.append(item)
        return {'files': files}
