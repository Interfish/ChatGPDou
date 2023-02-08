import os
import argparse
import time
import logging
from datetime import datetime

from chatgpdou import create_logger
from chatgpdou import LOG_DIR
from chatgpdou.douyin_live_cracker import DouyinLiveCracker


def main():
    parser = argparse.ArgumentParser(description='ChatGPDou')
    parser.add_argument("live_room_id", type=int, default=None)
    args = parser.parse_args()

    logger = create_logger("chatgpdou", log_file_path=os.path.join(
        LOG_DIR, datetime.now().strftime("%Y-%m-%d-%H-%M") + '.log'), log_level=logging.DEBUG)

    live_cracker = DouyinLiveCracker(args.live_room_id, logger=logger)
    while True:
        live_cracker.start_collect()
        time.sleep(10)
        live_cracker.stop_collect()
        time.sleep(10)


if __name__ == "__main__":
    main()
