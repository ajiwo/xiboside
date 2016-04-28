from xml.etree import ElementTree


def parse_file(path):
    layout = None
    try:
        _xlf = Xlf(path)
    except ElementTree.ParseError:
        return None
    except IOError:
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
            'id': node.attrib['id'],
            'width': node.attrib['width'],
            'height': node.attrib['height'],
            'left': node.attrib['left'],
            'top': node.attrib['top'],
            'media': [],
            'options': {}
        }

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
            'id': node.attrib['id'],
            'type': node.attrib['type'],
            'duration': node.attrib['duration'],
            'render': node.attrib['render'],
            'options': {},
            'raws': {}
        }

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
