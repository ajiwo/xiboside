import os
import json


class XiboConfig:
    def __init__(self, path=None):
        self.path = path
        self.saveDir = None
        self.url = None
        self.serverKey = None
        # datetime format (see strptime)
        self.strTimeFmt = None
        self.cmsTzOffset = None
        self.res_file_ext = None
        self.layout_file_ext = None

        self.load()
        pass

    @property
    def defaults(self):
        return {
            'saveDir': '/tmp/xibot',
            'url': 'http://localhost:8000',
            'serverKey': 'asdf',
            'strTimeFmt': '%Y-%m-%d %H:%M:%S',
            'cmsTzOffset': 7 * 3600,  # UTC+7
            'res_file_ext': '.html',
            'layout_file_ext': '.xml'
        }

    def load(self):
        tmp = {}
        if os.path.isfile(self.path):
            with open(self.path) as f:
                try:
                    tmp = json.load(f)
                except ValueError:
                    tmp = {}

        # load user configuration
        for k, v in tmp.iteritems():
            if getattr(self, k) is None:
                setattr(self, k, v)

        # load default values
        for k, v in self.defaults.iteritems():
            if getattr(self, k) is None:
                setattr(self, k, v)

    def save(self):
        data = {}
        for k, v in self.defaults.iteritems():
            if 'path' == k:
                continue
            data[k] = getattr(self, k)

        with open(self.path, 'w') as f:
            json.dump(data, f, indent=4, separators=(',', ': '))
