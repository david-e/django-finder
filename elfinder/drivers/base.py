import mimetypes
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from elfinder import models, utils as elutils

import logging

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
        'upload' : 'upload',
        'size'   : 'size',
        'file'   : 'file',
        'search' : 'search',
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

    def _append_info_if(self, vector, item, root, user, perm='read'):
        """
        Append inode informations if perm is available for the user
        """            
        if item.has_perm(perm, user):
            info = item.info(user)
            if item == root:
                info['phash'] = ''
            vector.append(info)
            return True
        return False

    def _extend_info_if(self, vector, items, root, user, perm='read'):
        for item in items:
            self._append_info_if(vector, item, user, perm)
        return vector

    def _children_tree(self, root, node, user=None):
        """
        Returns the tree starting from root INode object according to
        user permission
        """
        # create the vector of first-level children
        curr_node = node
        children, data = [], []
        i = 0
        while True:
            for item in curr_node.children.select_subclasses():
                if self._append_info_if(data, item, root, user):
                    children.append(item)
            if i >= len(data):
                break
            curr_node = children[i]
            i += 1
        logging.error('children %s' % children)
        return data

    def _ancestors_tree(self, root, node, siblings=False,
                        include_self=False, user=None):
        """
        Returns the tree from root to node INode object according to user
        permissions. Append siblings and self if required with paramenters
        """
        if not node:
            return []
        data = []
        curr_node = node if include_self else node.parent
        while curr_node:
            self._append_info_if(data, curr_node, root, user)
            if curr_node == root:
                break
            curr_node = curr_node.parent
        logging.error('root: %s, ancestors: %s' % (root, data))
        if siblings and node.parent:
            self._extend_info_if(data,
                node.parent.children.select_subclasses(), root, user)
        logging.error('with siblings: %s' % data)
        return data
    
    def _tree(self, root, target, user=None, tree=None):
        curr_node = self._get_inode(target)
        root_node = self._get_inode(root)
        data = self._children_tree(root_node, curr_node, user)
        # if tree == True data must contain also all ancestors and siblings of
        # the target
        if tree:
            data.extend(
                self._ancestors_tree(root_node, curr_node, siblings=True,
                                     include_self=True, user=user)
            )
        return data

    def _get_cwd(self, root, target, user=None):
        node = self._get_inode(target)
        cwd = node.info(user)
        if target == root:
            cwd['phash'] = ''
        return cwd
        

    def parents(self, root, target, user=None):
        tree = self._tree(root, target, tree=True, user=user)
        return {
            'parents': tree
        }
    
    def tree(self, root, target, user=None):
        tree = self._tree(root, target, user=user)
        return {
            'tree': tree
        }

    def open(self, root, target=None, tree=None,
             user=None):
        """
        Handles the open command
        """
        target = target or root
        files = self._tree(root, target, user=user, tree=tree)
        return {
            'files': files,
            'cwd': self._get_cwd(root, target, user)
        }
        
    def list(self, target, user=None, root=None):
        """
        Returns a list of files/directories in the target directory.
        """
        tree = self._tree(root, target, user=user)
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

    def upload(self, target, files, user=None):
        parent = self._get_inode(target)
        added = []
        if not parent.has_perm('add', user):
            raise PermissionDenied('You do not have permission \
                                    to add anything in %s' % parent.name)
        for key, value in files.items():
            # guess the type from the filename and get the class that handles it
            filename = value.name
            if self.inode_model.objects.filter(name=filename,
                    parent=parent).count() > 0:
                raise Exception('File %s already exists here!' % filename)
            # guess_type return a tuple (mimetype, extensions)
            mimetype = mimetypes.guess_type(filename)[0]
            FileKlass = self.inode_model.MIMETYPES.get(mimetype,
                                                       self.file_model)
            obj = FileKlass(
                name=filename,
                parent=parent,
                owner=user,
                data=value
            )
            obj.save()
            added.append(obj.info(user))
        return {
            'added': added
        }

    def file(self, target, user=None):
        inode = self._get_inode(target)
        if not inode.has_perm('read', user):
            raise PermissionDenied('You do not have permission \
                                    to read anything in %s' % inode.name)
        url = elutils.get_url(inode.data.name)
        return HttpResponseRedirect(url)

    def search(self, q, user=None, root=None):
        data = self._tree(root, root, user)
        logging.error('root: %s data: %s' % (root, data))
        files = []
        for item in data:
            if q in item['name']:
                files.append(item)
        return {
            'files': files,
        }
    