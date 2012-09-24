UI_OPTIONS =  {
    'toolbar': [
        ['back', 'forward'],
        ['download', 'mkdir', 'upload'],
        ['copy', 'cut', 'paste'],
        ['rm'],
        ['rename'],
        ['info', 'quicklook'],
        ['view', 'sort'],
        ['search'],
    ]
}


CONTEXT_MENU = {
    'navbar': ['open', '|', 'copy', 'cut', 'paste', '|', 'rm'],
    'cwd': ['reload', 'back', '|', 'mkdir', 'paste' '|', 'upload'],
    'files': ['edit', 'open', '|', 'copy', 'cut', 'paste', '|', 'rm', 'rename']
}


INIT_PARAMS = {
    'api': '2.0',
    'uplMaxSize': '1024M', 
    'options': {
        'separator': '/',
        'disabled': [],
        'archivers': {'create': [], 'extract': []},
        'copyOverwrite': 1,
    }
}


ALLOWED_HTTP_PARAMS = [
    'cmd', 'target', 'targets[]', 'current', 'tree',  'name', 'content', 'src', 
    'dst', 'cut', 'init', 'type', 'width', 'height', 'upload[]', 'q', 'root',
]
