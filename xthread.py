import base64
import calendar
import logging
import os
import time
from hashlib import md5

from PySide2.QtCore import QThread
from PySide2.QtCore import Signal
from PySide2.QtCore import Slot

import util
import xmds
import xmr

from Crypto.PublicKey import RSA


class XmdsThread(QThread):
    log = logging.getLogger('xiboside.XmdsThread')
    downloading_signal = Signal(str, str)
    downloaded_signal = Signal(object)
    layout_signal = Signal(str, str, tuple)

    def __init__(self, config, parent):
        super(XmdsThread, self).__init__(parent)
        self.config = config
        self.__mac_address = None
        self.__hardware_key = None
        self.__xmds_stop = False
        self.__xmds_running = False
        self.__xmr_pubkey = ''
        self.__xmr_channel = ''
        self.__ss_param = None
        self.single_shot = False
        self.layout_id = '0'
        self.schedule_id = '0'
        self.layout_time = (0, 0)
        if not os.path.isdir(config.saveDir):
            os.mkdir(config.saveDir, 0o700)
        self.xmdsClient = xmds.Client(config.url)
        self.xmdsClient.set_keys(config.serverKey)
        self.log.setLevel(logging.ERROR)

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
        self.quit()

    def __str_to_epoch(self, time_str):
        seconds = calendar.timegm(time.strptime(time_str, self.config.strTimeFmt))
        return seconds - self.config.cmsTzOffset

    def __epoch_to_str(self, time_str):
        seconds = float(time_str)
        return time.strftime(self.config.strTimeFmt, time.gmtime(seconds + self.config.cmsTzOffset))

    def __submit_stats(self):
        if isinstance(self.__ss_param, xmds.SubmitStatsParam):
            cl = self.xmdsClient
            resp = cl.send_request('SubmitStats', self.__ss_param)
            success = xmds.SuccessResponse().parse(resp)
            if success:
                self.__ss_param = None

    def __download(self, req_file_entry=None):
        if not req_file_entry or not req_file_entry.files:
            return None

        cl = self.xmdsClient
        self.__is_downloading = True
        get_resource_param = xmds.GetResourceParam()
        get_file_param = xmds.GetFileParam()
        for entry in req_file_entry.files:
            if self.__xmds_stop:
                break

            resp = None
            file_path = None
            downloaded = False
            if 'resource' == entry.type:
                file_path = "{0}/{1}_{2}_{3}{4}".format(self.config.saveDir,
                                                        entry.layoutid, entry.regionid,
                                                        entry.mediaid, self.config.res_file_ext)

                param = get_resource_param
                param.layoutId = entry.layoutid
                param.regionId = entry.regionid
                param.mediaId = entry.mediaid
                # print 'Downloading {0}'.format(file_path)
                self.downloading_signal.emit(entry.type, file_path)
                resp = cl.send_request('GetResource', param)
                if resp:
                    try:
                        with open(file_path, 'wb') as f:
                            f.write(resp.content.encode('utf-8'))
                            f.flush()
                            os.fsync(f.fileno())
                            downloaded = True
                    except IOError:
                        self.log.error('Download failed: %s' % file_path)
            elif entry.type in ('media', 'layout'):
                file_ext = ''
                if 'layout' == entry.type:
                    file_ext = self.config.layout_file_ext
                file_path = self.config.saveDir + '/' + entry.path + file_ext
                if md5sum_match(file_path, entry.md5):
                    # print 'Skipping {0}, md5sum match'.format(file_path)
                    continue
                param = get_file_param
                param.fileId = entry.id
                param.fileType = entry.type
                self.downloading_signal.emit(entry.type, file_path)

                try:
                    with open(file_path, 'wb') as f:
                        for offset in range(0, int(float(entry.size)), 1024*1024*2):
                            param.chuckSize = str(1024*1024*2)
                            param.chunkOffset = str(offset)
                            resp = cl.send_request('GetFile', param)
                            if resp:
                                f.write(resp.content)
                                f.flush()
                                os.fsync(f.fileno())
                                downloaded = True
                except IOError:
                    self.log.error('Download failed: %s' % file_path)

            if downloaded:
                self.downloaded_signal.emit(entry)
        # for entry ...

    def __xmds_cycle(self):
        self.__xmds_running = True
        self.__xmds_stop = False
        cl = self.xmdsClient
        param = xmds.RegisterDisplayParam()
        param.xmrChannel = self.__xmr_channel
        param.xmrPubKey = self.__xmr_pubkey
        sched_resp = xmds.ScheduleResponse()
        sched_cache = self.config.saveDir + '/schedule.xml'
        rf_cache = self.config.saveDir + '/rf.xml'
        collect_interval = 5
        while not self.__xmds_stop:
            self.log.info('__xmds_cycle started')
            display = cl.send_request('RegisterDisplay', param)

            if isinstance(display, xmds.RegisterDisplayResponse):
                if 'READY' == display.code:
                    collect_interval = display.details.get('collectInterval', 5)

            rf = cl.send_request('RequiredFiles')
            if isinstance(rf, xmds.RequiredFilesResponse):
                if not md5sum_match(rf_cache, rf.content_md5sum()):
                    rf.save_as(rf_cache)
                    self.__download(rf)

            schedule = cl.send_request('Schedule')
            if isinstance(schedule, xmds.ScheduleResponse):
                if not md5sum_match(sched_cache, schedule.content_md5sum()):
                    schedule.save_as(sched_cache)
            else:
                if sched_resp.parse_file(sched_cache):
                    schedule = sched_resp

            schedule_found = False
            if schedule and schedule.layouts:
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
            if schedule and not schedule_found:
                """ play default layout """
                self.layout_id = schedule.layout
                self.schedule_id = None
                self.layout_time = (0, 0)
            self.log.debug('emitting layout_sig(%s, %s, (%d, %d))' %
                           (self.layout_id, self.schedule_id, self.layout_time[0], self.layout_time[1]))
            self.layout_signal.emit(self.layout_id, self.schedule_id, self.layout_time)
            self.__submit_stats()
            if self.single_shot:
                break
            next_collect_time = time.time() + float(collect_interval)
            while time.time() < next_collect_time and not self.__xmds_stop:
                self.msleep(250)
        # while not ...
        self.__xmds_running = False
        self.log.info('__xmds_cycle() finished')
        if self.single_shot:
            self.quit()

    def run(self):
        if not self.__xmds_running:
            self.__xmds_cycle()
        self.log.debug('run() finished %d' % self.exec_())

    # def quit(self):
    #     self.stop()
    #     return super(XmdsThread, self).quit()

    def set_xmr_info(self, channel, pubkey):
        self.__xmr_channel = channel
        self.__xmr_pubkey = pubkey

    def queue_stats(self, type_, from_date, to_date, schedule_id, layout_id, media_id):
        if self.__ss_param is None:
            self.__ss_param = xmds.SubmitStatsParam()

        self.__ss_param.add(
            type_,
            self.__epoch_to_str(from_date),
            self.__epoch_to_str(to_date),
            schedule_id,
            layout_id,
            media_id
        )


class XmrThread(QThread):
    log = logging.getLogger('xiboside.XmrThread')
    message_signal = Signal(list)

    def __init__(self, config, parent):
        super(XmrThread, self).__init__(parent)
        self._config = config
        self._channel = ''
        self._pubkey = ''
        self._privkey = ''
        self._prepare_keys()
        self.__sub = xmr.Subscriber(self._config.xmrPubUrl, self._channel, self._handle_message)

    def run(self):
        self.__sub.run()

    def stop(self):
        self.__sub.stop()

    def _handle_message(self, messages):
        if messages[0] == '':
            pass  # heartbeat, sign that xmr setup is okay
        else:
            self._decrypt_message(messages)

    def _decrypt_message(self, messages):
        sealed_data = base64.decodestring(messages[1])
        env_key = base64.decodestring(messages[0])
        # TODO: just print the decrypted message for now
        print(util.openssl_open(sealed_data, env_key, self._privkey))

    def _prepare_keys(self):
        rsa = RSA.generate(2048)
        self._privkey = rsa.exportKey()
        self._pubkey = rsa.publickey().exportKey()
        self._channel = md5(("%d %s" % (time.time(), self._config.xmrPubUrl)).encode('utf-8')).hexdigest()

    @property
    def pubkey(self):
        return self._pubkey

    @property
    def channel(self):
        return self._channel


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
