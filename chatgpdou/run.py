import os
import argparse
import time
import logging
import multiprocessing
from datetime import datetime

from chatgpdou import create_logger
from chatgpdou import LOG_DIR
from chatgpdou import create_or_clean_folder
from chatgpdou.douyin import DouyinLiveWebSocketServer
from chatgpdou.douyin import QuestionSelector
from chatgpdou import CommunicationQueue
from chatgpdou.chatgpt import ChatGPTWebBot


def wss_worker(live_url_id, comm_queue, log_path, log_level):
    wss_server = DouyinLiveWebSocketServer(
        live_url_id, comm_queue, log_path=log_path, log_level=log_level)
    wss_server.run_forever()


def main():
    parser = argparse.ArgumentParser(description='ChatGPDou')
    parser.add_argument("live_url_id", nargs='?')
    parser.add_argument("--chrome_profile_directory", type=str, default=None)
    parser.add_argument("--chrome_user_data_dir", type=str, default=None)
    parser.add_argument("--log_level", type=str,
                        choices=["info", "debug"], default="info")
    args = parser.parse_args()

    log_level = logging.INFO
    if args.log_level == "debug":
        log_level = logging.DEBUG

    live_url_id = args.live_url_id

    logdir = os.path.join(LOG_DIR, datetime.now().strftime("%Y-%m-%d-%H-%M"))
    create_or_clean_folder(logdir)
    main_logger = create_logger("main",
                                log_file_path=os.path.join(logdir, 'main.log'),
                                log_level=log_level)

    if not live_url_id:
        # A real live broadcast
        web_bot = ChatGPTWebBot(chrome_user_data_dir=args.chrome_user_data_dir,
                                chrome_profile_directory=args.chrome_profile_directory,
                                logger=main_logger)
        web_bot.prepare_chat_page()
        live_url_id = input(
            ("1. Setup the live cast and make it going.\n"
             "2. Make sure the ChatGPT page is loaded ready.\n"
             "3. Enter the live url ID: "))

    comm_queue = CommunicationQueue(maxsize=500)
    p = multiprocessing.Process(target=wss_worker,
                                args=(int(live_url_id),
                                      comm_queue,
                                      os.path.join(logdir, 'wss_worker.log'),
                                      log_level))
    try:
        p.start()
        main_logger.info("wss_workper pid: {}".format(p.pid))
        qs = QuestionSelector(comm_queue,
                              logger=main_logger)
        while True:
            time.sleep(5)
            comm_queue.clear()
            web_bot.set_count_down(time_interval=30)
            q_text = qs.collect_and_select_question(time_interval=30)
            if q_text:
                web_bot.send_question(q_text)
                done = web_bot.wait_answer(timeout_sec=60)
    finally:
        p.terminate()
        p.join()
        p.close()


if __name__ == "__main__":
    main()
