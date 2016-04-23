import logging
import time

from PySide.QtCore import *
from PySide.QtGui import *
from PySide.QtWebKit import QWebView

import xthread


class MediaStopping:
    def __init__(self, view):
        self._view = None
        if isinstance(view, MediaView):
            self._view = view

    def wait(self, every=0.1, tries=10):
        if self._view:
            while self._view.is_playing() and tries > 0:
                tries -= 1
                time.sleep(every)

    def __enter__(self):
        if self._view:
            self._view.stop()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
            pass


class MediaView(QObject):
    """A view represents Xibo media"""
    started_signal = Signal()
    finished_signal = Signal()
    stopping_signal = Signal(dict)
    log = logging.getLogger('xiboside.MediaView')

    def __init__(self, parent=None):
        super(MediaView, self).__init__(parent)
        self._path = None
        self._duration = 0
        self._widget = None
        self._media = None
        self._started = 0
        self._playing = False
        self._finished = 0
        self._ready = False
        self._play_timer = QTimer(self)
        self._connect_signals()
        self.log.setLevel(logging.DEBUG)

    def _connect_signals(self):
        self.started_signal.connect(self.mark_started)
        self.finished_signal.connect(self.mark_finished)
        self._play_timer.setSingleShot(True)
        self.connect(self._play_timer, SIGNAL("timeout()"), self.stop)

    @Slot()
    def play(self):
        pass

    @Slot()
    def stop(self):
        pass

    @Slot()
    def mark_started(self):
        self._started = time.time()

    @Slot()
    def mark_finished(self):
        self._finished = time.time()

    def is_ready(self):
        return self._ready

    def is_started(self):
        return self._started > 0

    def is_playing(self):
        return self.is_started() and not self.is_finished()

    def is_finished(self):
        return self._finished > 0

    def set_media(self, media):
        self._media = media

    def set_default_widget_prop(self):
        if self._widget is not None:
            self._widget.setAttribute(Qt.WA_DeleteOnClose, False)
            self._widget.setFocusPolicy(Qt.NoFocus)
            self._widget.setContextMenuPolicy(Qt.NoContextMenu)

    def widget(self):
        return self._widget

    def set_geometry(self, left=0, top=0, width=100, height=100):
        self._widget.setGeometry(int(float(left)), int(float(top)), int(float(width)), int(float(height)))


class ImageMediaView(MediaView):
    def __init__(self, media=None, parent=None):
        super(ImageMediaView, self).__init__(parent)
        if media:
            self.set_media(media)
        self._widget = QLabel(parent)
        self.set_default_widget_prop()

    @Slot()
    def play(self):
        self.set_geometry(self._media['region']['left'], self._media['region']['top'],
                          self._media['region']['width'], self._media['region']['height'])

        path = "%s/%s" % (self._media['save_dir'], self._media['options']['uri'])

        rect = self._widget.geometry()
        img = QImage(path).scaled(rect.width(), rect.height(),
                                  Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self._widget.setPixmap(QPixmap.fromImage(img))
        self._widget.show()
        duration = int(self._media['duration']) * 1000
        self._play_timer.start(duration)
        self.started_signal.emit()

    @Slot()
    def stop(self):
        self.stopping_signal.emit(self._media)
        if self._widget:
            while not self._widget.close():
                time.sleep(0.25)
            del self._widget
            self._widget = None

        self.finished_signal.emit()


class VideoMediaView(MediaView):
    def __init__(self, media, parent=None):
        super(VideoMediaView, self).__init__(parent)
        if media:
            self.set_media(media)
        self.process = QProcess(parent)
        self._widget = QWidget(parent)
        self.set_default_widget_prop()
        self.connect(self.process, SIGNAL("readyReadStandardOutput()"), self.__grep_std_out)
        self.std_out = []

    @Slot()
    def play(self):
        self.set_geometry(self._media['region']['left'], self._media['region']['top'],
                          self._media['region']['width'], self._media['region']['height'])

        path = "%s/%s" % (self._media['save_dir'], self._media['options']['uri'])

        self._widget.show()
        args = [
            '-slave', '-identify', '-input',
            'nodefault-bindings:conf=/dev/null',
            '-wid', str(int(self._widget.winId())),
            path
        ]
        self.process.start('mplayer', args)
        self.started_signal.emit()

    @Slot()
    def stop(self):
        self.stopping_signal.emit(self._media)
        if self.process.isOpen():
            self.process.write("stop\n")
            if not self.process.waitForFinished(500):
                self.process.write("quit\n")
            if not self.process.waitForFinished(500):
                self.process.kill()

        if self.process.isOpen():
            self.process.close()

        if self._widget:
            while not self._widget.close():
                time.sleep(0.25)
            del self._widget
            self._widget = None
        self.finished_signal.emit()

    @Slot()
    def __grep_std_out(self):
        lines = self.process.readAllStandardOutput().split("\n")
        for line in lines:
            if not line.isEmpty():
                if line.startsWith("Starting playback"):
                    pass
                else:
                    part = line.split("=")
                    if 'ID_EXIT' == part[0]:
                        self.stop()
                    elif 'ID_LENGTH' == part[0]:
                        self._play_timer.stop()
                        self._play_timer.start(1000 * float(part[1]))


class WebMediaView(MediaView):
    def __init__(self, media, parent=None):
        super(WebMediaView, self).__init__(parent)
        if media:
            self.set_media(media)
        self._widget = QWebView(parent)
        self._widget.setDisabled(True)
        self._widget.page().mainFrame().setScrollBarPolicy(Qt.Vertical, Qt.ScrollBarAlwaysOff)
        self._widget.page().mainFrame().setScrollBarPolicy(Qt.Horizontal, Qt.ScrollBarAlwaysOff)
        self.set_default_widget_prop()

    @Slot()
    def play(self):
        self.set_geometry(self._media['region']['left'], self._media['region']['top'],
                          self._media['region']['width'], self._media['region']['height'])

        path = "%s/%s-%s-%s%s" % (
            self._media['save_dir'],
            self._media['layout_id'], self._media['region']['id'], self._media['id'],
            self._media['res_ext']
        )
        if 'webpage' == str(self._media['type']) and 'native' == str(self._media['render']):
            url = self._media['options']['uri']
            self._widget.load(QUrl.fromPercentEncoding(url))
        else:
            self._widget.load('file://' + path)
        self._widget.show()

        duration = float(self._media['duration']) * 1000
        self._play_timer.start(duration)
        self.started_signal.emit()

    @Slot()
    def stop(self):
        self.log.debug('stopping_signal.emit(%s)' % self._media['id'])
        self.stopping_signal.emit(self._media)
        if self._widget:
            self._widget.stop()
            while not self._widget.close():
                time.sleep(0.25)
            del self._widget
            self._widget = None

        self.finished_signal.emit()


class MainWindow(QMainWindow):
    log = logging.getLogger('xiboside.MainWindow')

    def __init__(self, config,  parent=None):
        super(MainWindow, self).__init__(parent)
        self._config = config

        self.__layout_id = None
        self.__layout_time = (0, 0)

        self.__mediaview_list = []
        self._setup_ui()

        self.__xmds_thread = xthread.XmdsThread(config, self)
        self.__play_thread = xthread.PlayThread(config, self)
        self._setup_threads()

        self.__layout_timer = QTimer(self)
        self.__layout_timer.setSingleShot(True)
        self.__layout_timer.timeout.connect(self.on_layout_timeout)
        self.log.setLevel(logging.DEBUG)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_all_media()
        self.__xmds_thread.quit()
        self.__play_thread.quit()
        if exc_tb or exc_type or exc_val:
            pass

    def recreate_play_thread(self):
        self.__play_thread.quit()
        self.__play_thread = xthread.PlayThread(self._config, self)
        self.__play_thread.play_layout_sig.connect(self.play_layout)
        self.__play_thread.play_media_sig.connect(self.play_media)
        self.__play_thread.start()

    def recreate_xmds_thread(self):
        self.__xmds_thread.quit()
        self.__xmds_thread = xthread.XmdsThread(self._config, self)
        self.__xmds_thread.layout_sig.connect(self.set_layout_id)
        self.__xmds_thread.downloaded_sig.connect(self.item_downloaded)
        self.__xmds_thread.start()

    def _setup_threads(self):
        self.__xmds_thread.layout_sig.connect(self.set_layout_id)
        self.__xmds_thread.downloaded_sig.connect(self.item_downloaded)
        self.__play_thread.play_layout_sig.connect(self.play_layout)
        self.__play_thread.play_media_sig.connect(self.play_media)
        self.__xmds_thread.start()
        self.__play_thread.start()

    def _setup_ui(self):
        self.setCentralWidget(QWidget(self))

    @Slot(str, tuple)
    def set_layout_id(self, layout_id, layout_time):
        self.log.debug('set_layout_id(%s, (%d, %d))' %
                       (layout_id, layout_time[0], layout_time[1]))

        if self.__layout_id != layout_id:
            self.log.debug('set_layout_id got different layout')
            self.stop_all_media()

        self.__play_thread.set_layout_id(layout_id, layout_time)
        self.__layout_id = layout_id
        self.__layout_time = layout_time

        if self.__layout_time[0] and self.__layout_time[1]:
            # If it's a scheduled layout, check the stop time, then schedule a stop
            self.__layout_timer.stop()
            t1 = layout_time[1] - time.time()
            self.__layout_timer.start(int(t1 * 1000))

    @Slot()
    def on_layout_timeout(self):
        """A timeout slot for expired scheduled-layout"""
        self.stop_all_media()
        self.recreate_play_thread()
        self.recreate_xmds_thread()

    def play_layout(self, layout, layout_id):
        if self.__layout_id != layout_id:
            self.__layout_id = layout_id

        if 'bgcolor' in layout:
            style = "QWidget {background-color: %s;}" % layout['bgcolor']
            self.setStyleSheet(style)

    def play_media(self, media):
        if self.__play_thread.playing_media_list.count(media):
            if 'image' == media['type']:
                self.play_image_media(media)
            elif 'video' == media['type']:
                self.play_video_media(media)
            else:
                self.play_web_media(media)

    @Slot()
    def stop_all_media(self):
        for view in self.__mediaview_list:
            with MediaStopping(view) as s:
                s.wait()
        del self.__mediaview_list[:]

    @Slot(str, str)
    def item_downloaded(self, item):
        if 'layout' == item.type and item.id == self.__layout_id:
            self.stop_all_media()
            self.recreate_play_thread()

    def append_mediaview(self, view):
        view.stopping_signal.connect(self.__play_thread.remove_media)
        self.__mediaview_list.append(view)

    def play_web_media(self, media):
        view = WebMediaView(media, self)
        if not self.__mediaview_list.count(view):
            view.play()
            self.append_mediaview(view)

    def play_image_media(self, media):
        view = ImageMediaView(media, self)
        if not self.__mediaview_list.count(view):
            view.play()
            self.append_mediaview(view)

    def play_video_media(self, media):
        view = VideoMediaView(media, self)
        if not self.__mediaview_list.count(view):
            view.play()
            self.append_mediaview(view)
