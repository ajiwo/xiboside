import base64
import exceptions
import logging
import os
import re
import sys
import uuid
from hashlib import md5
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
        self.__mac_address = None
        self.__client = None
        self.__set_identity()
        self.connect()

    def __set_identity(self):
        node = None
        if sys.platform == 'win32':
            for getter in [uuid._netbios_getnode, uuid._ipconfig_getnode]:
                node = getter()
                if node:
                    break
        else:
            # Linux only, find mac address using ifconfig command. taken from uuid._ifconfig_getnode
            for args in ('eth0', 'wlan0', 'en0'):  # TODO: other possible network interface name
                node = uuid._find_mac('ifconfig', args, ['hwaddr', 'ether'], lambda i: i + 1)
                if node:
                    break

        if node is None:
            raise RuntimeError("No network interface found.")
        self.__mac_address = ':'.join([str('%012x' % node)[x:x + 2] for x in range(0, 12, 2)])
        url = 'xiboside://%s/%s/%s' % (sys.platform, os.name, self.__mac_address)
        self.__keys['hardware'] = uuid.uuid3(uuid.NAMESPACE_URL, url)

    @property
    def mac_address(self):
        return self.__mac_address

    def was_connected(self):
        return self.__client and self.__client.wsdl is not None

    def connect(self):
        try:
            self.__client = SoapClient(self.__url + "/xmds.php?WSDL&v=" + str(self.__ver))
        except exceptions.IOError, err:
            log.error(err)
            self.__client = None

        return self.__client is not None

    def set_keys(self, server_key=None):
        self.__keys['server'] = server_key

    def send_request(self, method=None, params=None):
        if not self.was_connected():
            self.connect()
            return None

        response = None
        text = None
        tmp = None
        try:
            if 'registerDisplay'.lower() == method.lower():
                params.macAddress = self.__mac_address
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

            elif 'submitStats'.lower() == method.lower():
                text = self.__client.service.SubmitStats(self.__keys['server'], self.__keys['hardware'],
                                                         params.dumps())
                tmp = SuccessResponse()

        except SoapFault as err:
            log.error(err)
        except exceptions.IOError as err:
            log.error(err)

        if tmp and tmp.parse(text):
            response = tmp

        return response


class _XmdsResponse(object):
    def __init__(self):
        self.content = None

    def parse(self, text):
        return False

    def save_as(self, path):
        if not self.content:
            return 0
        try:
            with open(path, 'w') as f:
                f.write(self.content)
                f.flush()
                os.fsync(f.fileno())
            written = os.stat(path).st_size
        except IOError:
            written = 0
        return written

    def parse_file(self, path):
        try:
            with open(path, 'r') as f:
                return self.parse(f.read())
        except IOError:
            return False

    def content_md5sum(self):
        content = ''
        if self.content:
            content = self.content
        return md5(content).hexdigest()


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


class RequiredFilesResponse(_XmdsResponse):
    def __init__(self):
        super(RequiredFilesResponse, self).__init__()
        self.files = None

    def parse(self, text):
        if not text:
            return False

        # Remove id attribute for resource file, seems unrelated but always change.
        # doing this we can compute md5sum of the response then save a cache of this
        # response. see XmdsThread.__xmds_cycle
        text = re.sub(
            r'(type="resource")(\s+id=".*")(\s+layout)',
            r'\1\3',
            text
        )

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


class ScheduleResponse(_XmdsResponse):
    def __init__(self):
        super(ScheduleResponse, self).__init__()
        self.layout = ''
        self.layouts = []  # ScheduleLayoutEntry
        self.dependants = []

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


class GetFileResponse(_XmdsResponse):
    def __init__(self):
        super(GetFileResponse, self).__init__()

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


class GetResourceResponse(_XmdsResponse):
    def __init__(self):
        super(GetResourceResponse, self).__init__()

    def parse(self, text):
        if text and len(text) > 0:
            self.content = text
            return True

        return False


class _XmlParam(object):
    def __init__(self, tag):
        xml = '<?xml version="1.0" encoding="UTF-8" ?>'
        self._tag = xml + "\n<{0}>%s</{0}>".format(tag)
        self._tmp = ''

    def dumps(self):
        return self._tag % self._tmp


class MediaInventoryParam(_XmlParam):
    def __init__(self):
        super(MediaInventoryParam, self).__init__('files')

    def add(self, id_, complete, md5, last_checked):
        tmp = '<{} id="{}" complete="{}" md5="{}" lastChecked="{}" />'.format(
            'file', id_, complete, md5, last_checked
        )
        self._tmp += tmp


class SubmitLogParam(_XmlParam):
    def __init__(self):
        super(SubmitLogParam, self).__init__('logs')

    def add(self, date, category, type_, message, method, thread):
        tmp = '<{} date="{}" category="{}" type="{}" message="{}" method="{}" thread="{}" />'.format(
            'log', date, category, type_, message, method, thread
        )
        self._tmp += tmp


class SubmitStatsParam(_XmlParam):
    def __init__(self):
        super(SubmitStatsParam, self).__init__('stats')

    def add(self, type_, from_date, to_date, schedule_id, layout_id, media_id):
        self._tmp += '<{} type="{}" fromdt="{}" todt="{}" scheduleid="{}" layoutid="{}" mediaid="{}" />'.format(
            'stat', type_, from_date, to_date, schedule_id, layout_id, media_id
        )


class SuccessResponse(_XmdsResponse):
    def __init__(self):
        super(SuccessResponse, self).__init__()

    def parse(self, text):
        if text:
            self.content = text
            return True

        return False
