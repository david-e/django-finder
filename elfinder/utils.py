import os

from django.conf import settings


def get_path_for_upload(instance, filename, rel_path=None):
    """
    This method build the filename base on a path with structure yyyy/mm/dd
    and an available filename in that folder
    """
    if not rel_path:
        from datetime import datetime
        now = datetime.now()
        rel_path = '%4d/%02d/%02d' % (now.year, now.month, now.day)
    path = os.path.join(settings.MEDIA_ROOT, rel_path)
    # create directory if doesn't exist'
    if not os.path.exists(path):
        os.makedirs(path)
    i = 0
    while True:
        fullfilename = os.path.join(path, '%02d%s' % (i, filename))
        if not os.path.exists(fullfilename):
            break 
        i += 1
    return fullfilename


def get_url(filename):
    return '/' + filename.replace(settings.MEDIA_ROOT, settings.MEDIA_URL)