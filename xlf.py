from xml.etree import ElementTree
import logging
log = logging.getLogger('xiboside.xlf')


def parse_file(path):
    layout = None
    try:
        _xlf = Xlf(path)
    except ElementTree.ParseError, err:
        log.error(err.message)
        return None
    except IOError, err:
        log.error("%s: %s" % (err.strerror, err.filename))
        return None
    if _xlf.layout:
        layout = dict(_xlf.layout)
        _xlf = None
        del _xlf
    return layout


class Xlf:
    def __init__(self, path=None):
        self.layout = None
        self.region = None
        self.media = None
        if path:
            self.parse(path)

    def parse(self, path):
        layout = {
            'width': '',
            'height': '',
            'bgcolor': '',
            'background': '',
            'regions': [],
            'tags': []
        }
        tree = ElementTree.parse(path)
        root = tree.getroot()

        if 'layout' != root.tag:
            self.layout = None
            return None

        for k, v in root.attrib.iteritems():
            if k in layout:
                layout[k] = v

        for child in root:
            if 'region' == child.tag:
                region = self.__parse_region(child)
                if region:
                    layout['regions'].append(region)
            elif 'tags' == child.tag:
                for tag in child:
                    layout['tags'].append(tag.text)

        self.layout = layout
        return layout

    def __parse_region(self, node):
        if node is None:
            self.region = None
            return None

        region = {
            'id': '',
            'width': '',
            'height': '',
            'left': '',
            'top': '',
            'userId': '',
            'zindex': '0',
            'media': [],
            'options': {}
        }
        for k, v in node.attrib.iteritems():
            if k in region:
                region[k] = v

        for child in node:
            if 'media' == child.tag:
                media = self.__parse_media(child)
                if media:
                    region['media'].append(media)
            elif 'options' == child.tag:
                for option in child:
                    if option.text:
                        region['options'][option.tag] = option.text

        self.region = region
        return region

    def __parse_media(self, node):
        if node is None:
            self.media = None
            return None

        media = {
            'id': '',
            'type': '',
            'duration': '',
            'render': '',
            'options': {},
            'raws': {}
        }
        for k, v in node.attrib.iteritems():
            if k in media:
                media[k] = v

        for child in node:
            if 'options' == child.tag:
                for option in child:
                    if option.text:
                        media['options'][option.tag] = option.text
            elif 'raw' == child.tag:
                for raw in child:
                    if raw.text:
                        media['raws'][raw.tag] = raw.text

        self.media = media
        return media
