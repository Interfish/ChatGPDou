import os
import shutil
import logging
import time
import random
import multiprocessing
import multiprocessing.queues as mpq
from queue import Empty

PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
WEB_DRIVER_DIR = os.path.join(PROJECT_ROOT, 'chrome')


def create_logger(logger_name, log_level=logging.INFO, log_file_path=None, log_file_mode='w'):
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-5.5s]  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger = logging.getLogger(logger_name)
    logger.addHandler(console_handler)

    if log_file_path:
        file_handler = logging.FileHandler(
            log_file_path, mode=log_file_mode, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    logger.setLevel(log_level)
    return logger


def create_or_clean_folder(dir_path):
    os.makedirs(dir_path, exist_ok=True)
    shutil.rmtree(dir_path)
    os.makedirs(dir_path)


def random_delay(min_delay, max_delay):
    time.sleep(random.uniform(min_delay, max_delay))


class CommunicationQueue(mpq.Queue):
    def __init__(self, *args, **kwargs):
        ctx = multiprocessing.get_context()
        super(CommunicationQueue, self).__init__(*args, **kwargs, ctx=ctx)

    def get_no_throw(self, *args):
        try:
            return self.get(*args)
        except Empty:
            return None

    def clear(self):
        try:
            while True:
                self.get_nowait()
        except Empty:
            pass
