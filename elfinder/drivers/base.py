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

    def mkdir(self, name, parent, user=None):
        """
        Creates a directory.
        :param name: The name of the new directory.
        :param parent: The hash of the parent directory.
        :returns: dict -- a dict describing the new directory.
        """
        raise NotImplementedError

    def mkfile(self, name, parent, user=None):
        """
        Creates a directory.
        :param name: The name of the new file.
        :param parent: The hash of the parent directory.
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
    }

    def __init__(self, folder_model=models.FolderNode,
                 file_model=models.FileNode):
        self.file_model = file_model
        self.folder_model = folder_model

    def tree(self, target=models.INode.ROOT['HASH'], user=None):
        files, curr_dir_info = self._tree(target, False, user)
        # tree commands wants a 'tree' key instead of 'files' one.
        # So change it.
        return {'tree': files}

    def _tree(self, target=models.INode.ROOT['HASH'], tree=None,
              user=None):
        data = []
        folders = self.folder_model
        try:
            curr_dir = folders.objects.get_hash(target)
            curr_dir_info = curr_dir.info(user)
            print 'curr:', curr_dir
        except folders.DoesNotExist, folders.MultipleObjectsReturned:
            return []  # handle the error
        print 'children'
        for inode in curr_dir.children.select_subclasses():
            print inode
            data.append(inode.info(user))
        # if tree == True data must contain also all ancestors and siblings of
        # the target
        if tree:
            for item in curr_dir.get_ancestors(include_self=True):
                data.append(item.info(user=user))
                for item_siblings in item.get_siblings():
                    data.append(item_siblings.info(user))
        return data, curr_dir_info

    def open(self, target=models.INode.ROOT['HASH'], tree=None,
             user=None):
        """
        Handles the open command
        """
        files, curr_dir_info = self._tree(target, tree, user)
        return {'files': files, 'cwd': curr_dir_info}
        