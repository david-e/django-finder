from django.core.exceptions import PermissionDenied

from elfinder import models

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
        'open'   : 'open',
        'tree'   : 'tree',
        'list'   : 'list',
        'mkdir'  : 'mkdir',
        'rename' : 'rename',
        'rm'     : 'remove',
        'paste'  : 'paste',
        'parents': 'parents',
    #    'upload' : 'upload',
        'size'   : 'size',
    }

    def __init__(self, inode_model = models.INode,
                 folder_model=models.FolderNode, file_model=models.FileNode):
        self.inode_model = inode_model
        self.folder_model = folder_model
        self.file_model = file_model

    def _get_inode(self, target_hash):
        """
        Return the inode cast to subclasses
        """
        return self.inode_model.objects.get_hash(target_hash)

    def _tree(self, curr_dir, tree=None, user=None):
        data = []
        for inode in curr_dir.children.select_subclasses():
            data.append(inode.info(user))
        # if tree == True data must contain also all ancestors and siblings of
        # the target
        if tree:
            for item in curr_dir.get_ancestors(include_self=True):
                data.append(item.info(user=user))
                for item_siblings in item.get_siblings():
                    data.append(item_siblings.info(user))
        return data

    def parents(self, target, user=None):
        curr_dir = self._get_inode(target)
        tree = self._tree(curr_dir, tree=True, user=user)
        return {
            'parents': tree
        }
    
    def tree(self, target, user=None):
        curr_dir = self._get_inode(target)
        tree = self._tree(curr_dir, user=user)
        return {
            'tree': tree
        }

    def open(self, target=models.INode.ROOT['HASH'], tree=None,
             user=None):
        """
        Handles the open command
        """
        curr_dir = self._get_inode(target)
        files = self._tree(curr_dir, tree, user)
        return {
            'files': files,
            'cwd': curr_dir.info(user)
        }
        
    def list(self, target, user=None):
        """
        Returns a list of files/directories in the target directory.
        """
        curr_dir = self._get_inode(target)
        tree = self._tree(curr_dir, user=user)
        inode_list = [inode['name'] for inode in tree]
        return {
            'list': inode_list
        }

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
        return {
            'added': [new_dir.info(user)]
        }

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

    def _copy_inode(self, target, dst_dir):
        import copy
        new_inode = copy.copy(target)
            # so when save is called, django create a new pk
        new_inode.pk = new_inode.id = None
        new_inode.parent = dst_dir # set the new parent folder
        new_inode.save()
        return new_inode

    def paste(self, targets, src, dst, cut, user=None):
        removed, added = [], []
        src_dir = self._get_inode(src)
        dst_dir = self._get_inode(dst)
        for target in targets:
            inode = self._get_inode(target)
            # check read permission on target inode
            if not inode.has_perm('read', user):
                raise PermissionDenied('You do not have permission \
                                        to read %s' % inode.name)
            # check user permission on destination folder
            if not dst_dir.has_perm('add', user):
                raise PermissionDenied('You do not have permission \
                                        to read %s' % inode.name)
            # check if inode.name is not already present in destination folder
            if dst_dir.children.filter(name=inode.name).count():
                raise Exception('%s is already present in %s' % (inode.name,
                                                             dst_dir.name))
            new_inode = self._copy_inode(inode, dst_dir)
            added.append(new_inode.info(user))
            if cut == '1':
                if not inode.has_perm('remove', user):
                     raise PermissionDenied('You do not have permission \
                                            to remove %s' % inode.name)
                inode.delete()
                removed.append(target)
        return {
            'added': added,
            'removed': removed
        }

    def size(self, targets, user=None):
        size = 0
        for target in targets:
            inode = self._get_inode(target)
            size += inode.total_size
        return {
            'size': size
        }
    