import calendar
import logging
import os
import time
from hashlib import md5
from threading import Thread, currentThread

from PySide.QtCore import QThread, Signal, Slot

import xlf
import xmds


class XmdsThread(QThread):
    log = logging.getLogger('xiboside.XmdsThread')
    downloading_sig = Signal(str, str)
    downloaded_sig = Signal(object)
    layout_sig = Signal(str, str, tuple)

    __xmds_stop = False
    __xmds_running = False

    def __init__(self, config, parent):
        super(XmdsThread, self).__init__(parent)
        self.config = config
        self.__mac_address = None
        self.__hardware_key = None
        self.layout_id = None
        self.schedule_id = None
        self.layout_time = None
        if not os.path.isdir(config.saveDir):
            os.mkdir(config.saveDir, 0o700)
        # self.__set_identity()
        self.xmdsClient = xmds.Client(config.url)
        self.xmdsClient.set_keys(config.serverKey)
        self.log.setLevel(logging.DEBUG)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        if exc_tb or exc_type or exc_val:
            pass

    @Slot()
    def stop(self):
        self.__xmds_stop = True
        while self.__xmds_running:
            self.msleep(250)
            self.log.info('stop() waiting')
        self.log.info('stop() stopped')

    def __str_to_epoch(self, time_str):
        seconds = calendar.timegm(time.strptime(time_str, self.config.strTimeFmt))
        return seconds - self.config.cmsTzOffset

    def __download(self, req_file_entry=None):
        if not req_file_entry or not req_file_entry.files:
            return None

        cl = self.xmdsClient
        self.__is_downloading = True
        for entry in req_file_entry.files:
            if self.__xmds_stop:
                break

            resp = None
            file_path = None
            if 'resource' == entry.type:
                file_path = "{0}/{1}-{2}-{3}{4}".format(self.config.saveDir,
                                                        entry.layoutid, entry.regionid,
                                                        entry.mediaid, self.config.res_file_ext)

                param = xmds.GetResourceParam(entry.layoutid, entry.regionid, entry.mediaid)
                # print 'Downloading {0}'.format(file_path)
                self.downloading_sig.emit(entry.type, file_path)
                resp = cl.send_request('GetResource', param)
            elif entry.type in ('media', 'layout'):
                file_ext = ''
                if 'layout' == entry.type:
                    file_ext = self.config.layout_file_ext
                file_path = self.config.saveDir + '/' + entry.path + file_ext
                if md5sum_match(file_path, entry.md5):
                    # print 'Skipping {0}, md5sum match'.format(file_path)
                    continue

                param = xmds.GetFileParam(entry.id, entry.type, 0, entry.size)
                self.downloading_sig.emit(entry.type, file_path)
                resp = cl.send_request('GetFile', param)

            downloaded = False
            if resp:
                f = None
                try:
                    f = open(file_path, 'wb')
                except IOError:
                    pass
                finally:
                    if f:
                        f.write(resp.content)
                        f.flush()
                        os.fsync(f.fileno())
                        f.close()
                        downloaded = True

            if downloaded:
                self.downloaded_sig.emit(entry)
        # for entry ...

    def __xmds_cycle(self):
        self.__xmds_running = True
        self.__xmds_stop = False
        while not self.__xmds_stop:
            self.log.info('__xmds_cycle started')
            cl = self.xmdsClient
            param = xmds.RegisterDisplayParam()
            registered = cl.send_request('RegisterDisplay', param)

            if isinstance(registered, xmds.RegisterDisplayResponse):
                collect_interval = registered.details.get('collectInterval', 5)
            else:
                collect_interval = 5

            self.__download(cl.send_request('RequiredFiles'))
            schedule = cl.send_request('Schedule')
            if not schedule:
                self.msleep(1000)
                continue

            schedule_found = False
            if schedule.layouts:
                for layout in schedule.layouts:
                    from_time = self.__str_to_epoch(layout.fromdt)
                    to_time = self.__str_to_epoch(layout.todt)
                    now_time = time.time()
                    if from_time <= now_time <= to_time:
                        self.layout_id = layout.file
                        self.schedule_id = layout.scheduleid
                        self.layout_time = (from_time, to_time)
                        schedule_found = True
                        break  # simultaneous scheduled layout is not supported yet
                        #  ----+ stop on first scheduled layout
                # for layout ...
            # if schedule.layouts ...
            if not schedule_found:
                """ play default layout """
                self.layout_id = schedule.layout
                self.schedule_id = None
                self.layout_time = (0, 0)
            self.log.debug('emitting layout_sig(%s, %s, (%d, %d))' %
                           (self.layout_id, self.schedule_id, self.layout_time[0], self.layout_time[1]))
            self.layout_sig.emit(self.layout_id, self.schedule_id, self.layout_time)
            next_collect_time = time.time() + float(collect_interval)
            while time.time() < next_collect_time and not self.__xmds_stop:
                self.msleep(250)
        # while not ...
        self.__xmds_running = False
        self.log.info('__xmds_cycle() finished')

    def run(self):
        if not self.__xmds_running:
            self.__xmds_cycle()
        self.log.debug('run() finished %d' % self.exec_())

    def quit(self):
        self.stop()
        return super(XmdsThread, self).quit()


class PlayThread(QThread):
    log = logging.getLogger('xiboside.PlayThread')
    play_layout_sig = Signal(dict)
    play_region_sig = Signal(dict)
    play_media_sig = Signal(dict)
    layout_expired_sig = Signal(str)

    playing_media_list = None

    def __init__(self, config, parent):
        super(PlayThread, self).__init__(parent)
        self.__play_running = False
        self.__play_stop = False
        self.__layout_id = None
        self.__schedule_id = None
        self.__layout_time = (0, 0)
        self.config = config
        if self.playing_media_list is None:
            self.playing_media_list = []
        self.log.setLevel(logging.DEBUG)

    @Slot(str)
    def set_layout_id(self, layout_id, schedule_id, layout_time):
        self.__layout_id = layout_id
        self.__schedule_id = schedule_id
        self.__layout_time = layout_time

    @Slot()
    def stop(self):
        self.__play_stop = True
        while self.__play_running or len(self.playing_media_list) > 0:
            self.msleep(200)
            self.log.info('stop() waiting %d media' % len(self.playing_media_list))

        self.log.info('stop() stopped')

    def __play_cycle(self):
        self.__play_running = True
        self.__play_stop = False
        # last_id = None
        while not self.__play_stop:
            if not self.__layout_id:
                self.msleep(250)
                continue
            # if last_id == self.__layout_id:
            #     same_id = True
            # else:
            #     last_id = self.__layout_id
            #     same_id = False

            file_path = self.config.saveDir + '/' + self.__layout_id + self.config.layout_file_ext
            xlf_layout = xlf.Xlf(file_path)
            if xlf_layout:
                layout = xlf_layout.layout
                layout['id'] = self.__layout_id
                layout['schedule_id'] = self.__schedule_id
                self.play_layout_sig.emit(layout)
                self.__play_layout(layout)
                self.log.info('__play_layout finished')
            # if not same_id:
            #     pass
            self.msleep(200)
        # while not ...
        self.log.info('__play_cycle finished')
        self.__play_running = False

    def __play_layout(self, layout):
        if layout is None:
            return None
        if self.__play_stop:
            return None

        threads = []

        for region in layout['regions']:
            region['layout_id'] = layout['id']
            region['schedule_id'] = layout['schedule_id']
            t = Thread(target=self.__play_region, name='__play_region_{0}'.format(region['id']), args=(region,))
            t.setDaemon(True)
            t.start()
            threads.append(t)

        self.msleep(100)
        for t in threads:
            t.join()
        # while [t.isAlive() for t in threads].count(True) > 0:
        #     time.sleep(0.25)

    def __play_region(self, region):
        if not region:
            return None

        loop = False
        if 'loop' in region['options']:
            loop = bool(int(region['options']['loop']))

        while not self.__play_stop:
            self.play_region_sig.emit(region)
            self.log.info(currentThread().getName() + ' Starting')
            for media in region['media']:
                media['layout_id'] = region['layout_id']
                media['schedule_id'] = region['schedule_id']
                media['region'] = {
                    'id': region['id'],
                    'left': region['left'],
                    'top': region['top'],
                    'width': region['width'],
                    'height': region['height']
                }
                media['save_dir'] = self.config.saveDir
                media['res_ext'] = self.config.res_file_ext
                self.__play_media(media)
            if not loop:
                break
        self.log.info(currentThread().getName() + ' Finished')

    def media_listed(self, media):
        listed = self.playing_media_list.count(media)
        return listed

    def remove_media(self, media):
        self.log.debug('remove_media(%s)' % media['id'])
        if self.media_listed(media):
            self.playing_media_list.remove(media)
            self.log.debug('remove_media(%s) removed' % media['id'])

    def __play_media(self, media):
        if media is None or self.__play_stop:
            return None

        self.log.info('__play_media_%s' % media['id'])
        if self.media_listed(media):
            self.log.info('Skip playing media %s' % media['id'])
            return None

        self.play_media_sig.emit(media)
        self.playing_media_list.append(media)

        while not self.__play_stop:
            if not self.media_listed(media):
                break
            self.msleep(250)
        self.log.info('__play_media_%s finished' % media['id'])

        self.remove_media(media)

    def run(self):
        if not self.__play_running:
            self.__play_cycle()
        else:
            self.log.debug('run() skipped, already running...')
        self.log.debug('run() finished %d' % self.exec_())

    def quit(self):
        self.stop()
        return super(PlayThread, self).quit()


def md5sum_match(file_path, md5sum):
    if not os.path.isfile(file_path):
        return False

    f = None
    content = None
    try:
        f = open(file_path, 'rb')
    finally:
        if f:
            content = f.read()
        f.close()
    if not content:
        return False

    return md5(content).hexdigest() == md5sum
