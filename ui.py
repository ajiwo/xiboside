import time

from PySide2.QtCore import QThread
from PySide2.QtCore import QTimer
from PySide2.QtWidgets import QMainWindow
from PySide2.QtWidgets import QWidget

import xlf
from xlfview import RegionView
from xthread import XmdsThread
from xthread import XmrThread


class CentralWidget(QWidget):
    def __init__(self, xmds, parent):
        super(CentralWidget, self).__init__(parent)
        self._xmds = xmds

    def queue_stats(self, type_, from_date, to_date, schedule_id, layout_id, media_id):
        self._xmds.queue_stats(type_, from_date, to_date, schedule_id, layout_id, media_id)


class MainWindow(QMainWindow):
    def __init__(self, config):
        super(MainWindow, self).__init__()
        self._schedule_id = '0'
        self._config = config
        self._region_view = []
        self._xmds = None
        self._xmr = None
        self._running = False

        self._layout_id = None
        self._layout_time = (0, 0)
        self.setup_xmr()
        self.setup_xmds()
        self._central_widget = CentralWidget(self._xmds, self)
        self._layout_timer = QTimer()
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(self.stop)
        self.setCentralWidget(self._central_widget)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        self._xmds.stop()
        if self._xmr:
            self._xmr.stop()
        if exc_tb or exc_type or exc_val:
            pass

    def setup_xmds(self):
        self._xmds = XmdsThread(self._config, self)
        self._xmds.layout_signal.connect(self.set_layout)
        self._xmds.downloaded_signal.connect(self.item_downloaded)
        if self._config.xmdsVersion > 4:
            self._xmds.set_xmr_info(self._xmr.channel, self._xmr.pubkey)
        self._xmds.start(QThread.IdlePriority)

    def setup_xmr(self):
        if self._config.xmdsVersion > 4:
            self._xmr = XmrThread(self._config, self)
            self._xmr.start(QThread.IdlePriority)

    def set_layout(self, layout_id, schedule_id, layout_time):
        if self._layout_id != layout_id:
            self.stop()
            self.play(layout_id, schedule_id)

        self._layout_id = layout_id
        self._schedule_id = schedule_id
        self._layout_time = layout_time

        if schedule_id and layout_time[1]:
            stop_time = layout_time[1] - time.time()
            self._layout_timer.setInterval(int(stop_time * 1000))
            self._layout_timer.start()

    def item_downloaded(self, entry):
        if 'layout' == entry.type and self._layout_id == entry.id:
            self.stop()
            self.play(self._layout_id, self._schedule_id)

    def play(self, layout_id, schedule_id):
        path = "%s/%s%s" % (self._config.saveDir, layout_id, self._config.layout_file_ext)
        layout = xlf.parse_file(path)
        if not layout:
            return False

        self._schedule_id = schedule_id
        self.setStyleSheet('background-color: %s' % layout['bgcolor'])
        for region in layout['regions']:
            region['_layout_id'] = layout_id
            region['_schedule_id'] = self._schedule_id
            region['_save_dir'] = self._config.saveDir
            view = RegionView(region, self._central_widget)
            self._region_view.append(view)
            view.play()

        return True

    def stop(self):
        if self._region_view:
            for view in self._region_view:
                view.stop()
        del self._region_view[:]
        self._central_widget = None
        self._central_widget = CentralWidget(self._xmds, self)
        self.setCentralWidget(self._central_widget)
