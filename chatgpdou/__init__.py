import os
import logging

PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')

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
