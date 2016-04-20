import base64
import exceptions
import logging
import uuid
from suds import WebFault as SoapFault
from suds.client import Client as SoapClient
from xml.etree import ElementTree

logging.basicConfig(level=logging.ERROR)
logging.getLogger('suds.client').setLevel(logging.WARNING)
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class Client:
    def __init__(self, url, ver=4):
        self.__keys = {
            'server': '',
            'hardware': ''
        }
        self.__url = url
        self.__ver = ver
        self.__client = None
        self.connect()

    def was_connected(self):
        return self.__client and self.__client.wsdl is not None

    def connect(self):
        try:
            self.__client = SoapClient(self.__url + "/xmds.php?WSDL&v=" + str(self.__ver))
        except exceptions.IOError, err:
            log.error(err)
            self.__client = None

        return self.__client is not None

    def set_keys(self, server=None, hardware=None):
        self.__keys['server'] = server
        if hardware and isinstance(hardware, uuid.UUID):
            self.__keys['hardware'] = str(hardware)

    def send_request(self, method=None, params=None):
        if not self.was_connected():
            self.connect()
            return None

        response = None
        text = None
        tmp = None
        try:
            if 'registerDisplay'.lower() == method.lower():
                text = self.__client.service.RegisterDisplay(self.__keys['server'], self.__keys['hardware'],
                                                             getattr(params, 'name'), getattr(params, 'type'),
                                                             getattr(params, 'version'), getattr(params, 'code'),
                                                             getattr(params, 'os'), getattr(params, 'macAddress'))
                tmp = RegisterDisplayResponse()

            elif 'requiredFiles'.lower() == method.lower():
                text = self.__client.service.RequiredFiles(self.__keys['server'], self.__keys['hardware'])
                tmp = RequiredFilesResponse()

            elif 'schedule' == method.lower():
                text = self.__client.service.Schedule(self.__keys['server'], self.__keys['hardware'])
                tmp = ScheduleResponse()

            elif 'getFile'.lower() == method.lower():
                text = self.__client.service.GetFile(self.__keys['server'], self.__keys['hardware'],
                                                     getattr(params, 'fileId'), getattr(params, 'fileType'),
                                                     getattr(params, 'chunkOffset'), getattr(params, 'chuckSize'))
                tmp = GetFileResponse()

            elif 'getResource'.lower() == method.lower():
                text = self.__client.service.GetResource(self.__keys['server'], self.__keys['hardware'],
                                                         getattr(params, 'layoutId'), getattr(params, 'regionId'),
                                                         getattr(params, 'mediaId'))
                tmp = GetResourceResponse()

        except SoapFault as err:
            log.error(err)
        except exceptions.IOError as err:
            log.error(err)

        if tmp and tmp.parse(text):
            response = tmp

        return response


class RegisterDisplayParam:
    def __init__(self, display_name='xiboside', display_type='android', version='1.0',
                 code=1, operating_system='Linux', mac_address=''):
        self.name = display_name
        self.type = display_type
        self.version = version
        self.code = code
        self.os = operating_system
        self.macAddress = mac_address


class RegisterDisplayResponse:
    def __init__(self):
        self.status = None
        self.code = None
        self.message = None
        self.version_instructions = None
        self.details = {}
        self.content = None

    def parse(self, text):
        if not text:
            return False

        root = ElementTree.fromstring(text)
        if 'display' != root.tag:
            return 0

        for key, val in root.attrib.iteritems():
            if hasattr(self, key):
                setattr(self, key, val)

        for detail in root:
            if detail.text:
                self.details[detail.tag] = detail.text

        self.content = text
        return True


class RequiredFilesEntry:
    def __init__(self):
        self.type = ''
        self.id = ''
        self.size = 0
        self.md5 = ''
        self.download = ''
        self.path = ''
        self.layoutid = ''
        self.regionid = ''
        self.mediaid = ''
        self.updated = 0


class RequiredFilesResponse:
    def __init__(self):
        self.files = None
        self.content = None

    def parse(self, text):
        if not text:
            return False

        root = ElementTree.fromstring(text)
        if 'files' != root.tag:
            return False

        self.files = []
        for child in root:
            if not 'file' == child.tag:
                continue
            entry = RequiredFilesEntry()
            for key, val in child.attrib.iteritems():
                if hasattr(entry, key):
                    setattr(entry, key, val)

            self.files.append(entry)
        # for child ...
        self.content = text
        return True


class ScheduleLayoutEntry:
    def __init__(self):
        self.file = None
        self.fromdt = None
        self.todt = None
        self.scheduleid = None
        self.priority = None
        self.dependents = None


class ScheduleResponse:
    def __init__(self):
        self.layout = ''
        self.layouts = []  # ScheduleLayoutEntry
        self.dependants = []
        self.content = None

    def parse(self, text):
        if not text:
            return False

        root = ElementTree.fromstring(text)
        if 'schedule' != root.tag:
            return False

        for child in root:
            if 'layout' == child.tag:
                layout = ScheduleLayoutEntry()
                for key, val in child.attrib.iteritems():
                    if hasattr(layout, key):
                        setattr(layout, key, val)
                self.layouts.append(layout)

            elif 'default' == child.tag:
                for key, val in child.attrib.iteritems():
                    if 'file' == key:
                        self.layout = val

            elif 'dependants' == child.tag:
                for dep in child:
                    if dep.text:
                        self.dependants.append(dep.text)

        self.content = text
        return True


class GetFileParam:
    def __init__(self, file_id='', file_type='', offset=0, size=0):
        self.fileId = file_id
        self.fileType = file_type
        self.chunkOffset = offset
        self.chuckSize = size


class GetFileResponse:
    def __init__(self):
        self.content = None

    def parse(self, text):
        if text and len(text) > 0:
            self.content = base64.decodestring(text)
            return True

        return False


class GetResourceParam:
    def __init__(self, layout_id='', region_id='', media_id=''):
        self.layoutId = layout_id
        self.regionId = region_id
        self.mediaId = media_id


class GetResourceResponse:
    def __init__(self):
        self.content = None

    def parse(self, text):
        if text and len(text) > 0:
            self.content = text
            return True

        return False
