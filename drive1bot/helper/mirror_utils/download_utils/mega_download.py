import threading
from pathlib import Path
from pymegasdkrest import MegaSdkRestClient
from drive1bot.helper.ext_utils.bot_utils import setInterval
from drive1bot import log, download_dict, download_dict_lock, OneDriveLog
from drive1bot.helper.mirror_utils.status_utils.mega_status import MegaDownloadStatus

log = OneDriveLog()


class MegaDownloader:
    POLLING_INTERVAL = 2

    def __init__(self, listener):
        super().__init__()
        self.__listener = listener
        self.__name = ""
        self.__gid = ''
        self.__resource_lock = threading.Lock()
        self.__mega_client = MegaSdkRestClient('http://localhost:6969')
        self.__periodic = None
        self.__downloaded_bytes = 0
        self.__progress = 0
        self.__size = 0


    @property
    def progress(self):
        with self.__resource_lock:
            return self.__progress

    @property
    def downloaded_bytes(self):
        with self.__resource_lock:
            return self.__downloaded_bytes

    @property
    def size(self):
        with self.__resource_lock:
            return self.__size

    @property
    def gid(self):
        with self.__resource_lock:
            return self.__gid

    @property
    def name(self):
        with self.__resource_lock:
            return self.__name

    @property
    def download_speed(self):
        if self.gid is not None:
            return self.__mega_client.getstatus(self.gid)['speed']

    def __onDownloadStart(self, name, size, gid):
        self.__periodic = setInterval(self.POLLING_INTERVAL, self.__onInterval)
        with download_dict_lock:
            download_dict[self.__listener.uid] = MegaDownloadStatus(self, self.__listener)
        with self.__resource_lock:
            self.__name = name
            self.__size = size
            self.__gid = gid
        self.__listener.onDownloadStarted()

    def __onInterval(self):
        dlInfo = self.__mega_client.getstatus(self.gid)
        if (
            dlInfo['is_completed'] == True or 
            dlInfo['is_cancelled'] == True or 
            dlInfo['is_failed'] == True
        ) and self.__periodic is not None:
             self.__periodic.cancel()
        if dlInfo['is_completed'] == True:
            self.__onDownloadComplete()
            return
        if dlInfo['is_cancelled'] == True:
            self.__onDownloadError('Cancelled by user')
            return
        if dlInfo['is_failed'] == True:
            self.__onDownloadError(dlInfo['error_string'])
            return
        self.__onDownloadProgress(dlInfo['completed_length'], dlInfo['total_length'])

    def __onDownloadProgress(self, current, total):
        with self.__resource_lock:
            self.__downloaded_bytes = current
            try:
                self.__progress = current / total * 100
            except ZeroDivisionError:
                self.__progress = 0

    def __onDownloadError(self, error):
        self.__listener.onDownloadError(error)

    def __onDownloadComplete(self):
        self.__listener.onDownloadComplete()

    def add_download(self, link, path):
        Path(path).mkdir(parents=True, exist_ok=True)
        dl = self.__mega_client.adddownload(link, path)
        gid = dl['gid']
        info = self.__mega_client.getstatus(gid)
        file_name = info['name']
        file_size = info['total_length']
        self.__onDownloadStart(file_name, file_size, gid)
        log.info(f'Started mega download with gid: {gid}')

    def cancel_download(self):
        log.info(f'Cancelling download on user request: {self.gid}')
        self.__mega_client.canceldownload(self.gid)