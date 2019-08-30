import os
import signal
import time

from PySide2.QtCore import QObject
from PySide2.QtCore import QProcess
from PySide2.QtCore import QRect
from PySide2.QtCore import QTimer
from PySide2.QtCore import QUrl
from PySide2.QtCore import Qt
from PySide2.QtCore import SIGNAL
from PySide2.QtCore import Signal
from PySide2.QtCore import Slot
from PySide2.QtGui import QImage
from PySide2.QtWidgets import QLabel
from PySide2.QtGui import QPixmap
from PySide2.QtWidgets import QWidget
from PySide2.QtWebEngineWidgets import QWebEngineView as QWebView


class MediaView(QObject):
    started_signal = Signal()
    finished_signal = Signal()

    def __init__(self, media, parent):
        super(MediaView, self).__init__(parent)
        self._parent = parent
        self._id = media['id']
        self._type = media['type']
        self._duration = media['duration']
        self._render = media['render']
        self._options = media['options']
        self._raws = media['raws']

        self._layout_id = media['_layout_id']
        self._schedule_id = media['_schedule_id']
        self._region_id = media['_region_id']
        self._save_dir = media['_save_dir']

        self._widget = None
        self._play_timer = QTimer(self)

        self._started = 0
        self._finished = 0

        self._errors = None
        # self.setObjectName('Media-%s-%s' % (self._type, self._id))
        # self._play_timer.setObjectName('%s-timer' % self.objectName())
        self._connect_signals()

    def _connect_signals(self):
        self.started_signal.connect(self.mark_started)
        self.finished_signal.connect(self.mark_finished)
        self._play_timer.setSingleShot(True)
        self.connect(self._play_timer, SIGNAL("timeout()"), self.stop)

    @staticmethod
    def make(media, parent):
        if 'type' not in media:
            return None

        if 'image' == media['type']:
            view = ImageMediaView(media, parent)
        elif 'video' == media['type']:
            view = VideoMediaView(media, parent)
        else:
            view = WebMediaView(media, parent)

        return view

    @Slot()
    def play(self):
        pass

    @Slot()
    def stop(self, delete_widget=False):
        if self.is_finished():
            return False
        if self._widget:
            tries = 10
            while tries > 0 and not self._widget.close():
                tries -= 1
                time.sleep(0.05)
            if delete_widget:
                del self._widget
                self._widget = None

        self.finished_signal.emit()
        return True

    @Slot()
    def mark_started(self):
        self._started = time.time()

    @Slot()
    def mark_finished(self):
        if not self.is_finished():
            self._finished = time.time()
            self._parent.queue_stats(
                'media',
                self._started,
                self._finished,
                self._schedule_id,
                self._layout_id,
                self._id
            )

    def is_started(self):
        return self._started > 0

    def is_finished(self):
        return self._finished > 0

    def is_playing(self):
        return self.is_started() and not self.is_finished()

    def set_default_widget_prop(self):
        if self._widget is not None:
            self._widget.setAttribute(Qt.WA_DeleteOnClose, False)
            self._widget.setFocusPolicy(Qt.NoFocus)
            self._widget.setContextMenuPolicy(Qt.NoContextMenu)
            self._widget.setObjectName('%s-widget' % self.objectName())


class ImageMediaView(MediaView):
    def __init__(self, media, parent):
        super(ImageMediaView, self).__init__(media, parent)
        self._widget = QLabel(parent)
        self._widget.setGeometry(media['_geometry'])
        self._img = QImage()
        self.set_default_widget_prop()

    @Slot()
    def play(self):
        self._finished = 0
        path = "%s/%s" % (self._save_dir, self._options['uri'])
        rect = self._widget.geometry()
        self._img.load(path)
        self._img = self._img.scaled(rect.width(), rect.height(),
                                     Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        self._widget.setPixmap(QPixmap.fromImage(self._img))
        self._widget.show()
        self._widget.raise_()

        self._play_timer.setInterval(int(float(self._duration) * 1000))
        self._play_timer.start()
        self.started_signal.emit()


class VideoMediaView(MediaView):
    def __init__(self, media, parent):
        super(VideoMediaView, self).__init__(media, parent)
        self._widget = QWidget(parent)
        self._process = QProcess(self._widget)
        self._process.setObjectName('%s-process' % self.objectName())
        self._std_out = []
        self._errors = []
        self._stopping = False
        self._mute = False
        if 'mute' in self._options:
            self._mute = bool(int(self._options['mute']))

        self._widget.setGeometry(media['_geometry'])
        self.connect(self._process, SIGNAL("error()"), self._process_error)
        self.connect(self._process, SIGNAL("finished()"), self.stop)
        self.connect(self._process, SIGNAL("readyReadStandardOutput()"), self.__grep_std_out)
        self.set_default_widget_prop()

        self._stop_timer = QTimer(self)
        self._stop_timer.setSingleShot(True)
        self._stop_timer.setInterval(1000)
        self._stop_timer.timeout.connect(self._force_stop)

    @Slot()
    def _force_stop(self):
        os.kill(self._process.pid(), signal.SIGTERM)
        self._stopping = False
        if not self.is_started():
            self.started_signal.emit()
        super(VideoMediaView, self).stop()

    @Slot(object)
    def _process_error(self, err):
        self._errors.append(err)
        self.stop()

    @Slot()
    def play(self):
        self._finished = 0
        path = "%s/%s" % (self._save_dir, self._options['uri'])
        self._widget.show()
        args = [
            '-slave', '-identify', '-input',
            'nodefault-bindings:conf=/dev/null',
            '-wid', str(int(self._widget.winId())),
            path
        ]
        if self._mute:
            args += ['-ao', 'null']

        self._process.start('mplayer', args)
        self._stop_timer.start()

    @Slot()
    def stop(self, delete_widget=False):
        if self._stopping or self.is_finished():
            return False
        self._stop_timer.start()
        self._stopping = True
        if self._process.state() == QProcess.ProcessState.Running:
            self._process.write("quit\n")
            self._process.waitForFinished(50)
            self._process.close()

        super(VideoMediaView, self).stop(delete_widget)
        self._stopping = False
        self._stop_timer.stop()
        return True

    @Slot()
    def __grep_std_out(self):
        lines = self._process.readAllStandardOutput().split("\n")
        for line in lines:
            if not line.isEmpty():
                if line.startsWith("Starting playback"):
                    self._widget.raise_()
                    self._play_timer.start()
                    self.started_signal.emit()
                    self._stop_timer.stop()
                else:
                    part = line.split("=")
                    if 'ID_LENGTH' == part[0]:
                        if float(self._duration) > 0:  # user set the video duration manually.
                            self._play_timer.setInterval(int(1000 * float(self._duration)))
                        else:  # use duration found by mplayer.
                            self._play_timer.setInterval(int(1000 * float(part[1])))


class WebMediaView(MediaView):
    def __init__(self, media, parent):
        super(WebMediaView, self).__init__(media, parent)
        self._widget = QWebView(parent)
        self._widget.setGeometry(media['_geometry'])
        self.set_default_widget_prop()
        self._widget.setDisabled(True)
        # self._widget.page().mainFrame().setScrollBarPolicy(Qt.Vertical, Qt.ScrollBarAlwaysOff)
        # self._widget.page().mainFrame().setScrollBarPolicy(Qt.Horizontal, Qt.ScrollBarAlwaysOff)

    @Slot()
    def play(self):
        self._finished = 0
        path = "%s/%s_%s_%s.html" % (
            self._save_dir,
            self._layout_id, self._region_id, self._id
        )
        self._widget.load("about:blank")
        if 'webpage' == str(self._type) and 'native' == str(self._render):
            url = self._options['uri']
            self._widget.load(QUrl.fromPercentEncoding(url))
        else:
            self._widget.load('file://' + path)
        self._widget.show()
        self._widget.raise_()

        self._play_timer.setInterval(int(float(self._duration) * 1000))
        self._play_timer.start()
        self.started_signal.emit()


class RegionView:
    def __init__(self, region, parent):
        self._parent = parent
        self._id = region['id']
        self._width = region['width']
        self._height = region['height']
        self._left = region['left']
        self._top = region['top']
        self._media = region['media']
        self._options = region['options']
        self._loop = False
        if 'loop' in self._options:
            self._loop = bool(int(self._options['loop']))

        self._layout_id = region['_layout_id']
        self._schedule_id = region['_schedule_id']
        self._save_dir = region['_save_dir']

        self._media_view = None
        self._media_index = 0
        self._media_length = 0
        self._stop = False
        self._populate_media()

    def _populate_media(self):
        self._media_view = []

        for media in self._media:
            media['_layout_id'] = self._layout_id
            media['_schedule_id'] = self._schedule_id
            media['_region_id'] = self._id
            media['_save_dir'] = self._save_dir
            media['_geometry'] = QRect(
                int(float(self._left)), int(float(self._top)),
                int(float(self._width)), int(float(self._height))
            )
            view = MediaView.make(media, self._parent)
            view.finished_signal.connect(self.play_next)
            self._media_view.append(view)
            self._media_length += 1
        # for media ...

    def play(self):
        if self._stop or self._media_length < 1:
            return None
        self._media_view[self._media_index].play()

    def play_next(self):
        self._media_index += 1
        if self._loop:
            if self._media_index >= self._media_length:
                self._media_index = 0

        if self._media_index < self._media_length:
            self.play()

    def stop(self):
        self._stop = True
        for view in self._media_view:
            if view.is_playing():
                view.stop(delete_widget=True)

        del self._media_view[:]

