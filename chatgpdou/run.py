import os
import argparse
import time
import logging
import multiprocessing
from datetime import datetime

from chatgpdou import create_logger
from chatgpdou import LOG_DIR, WEB_DRIVER_DIR
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
    parser.add_argument("--web_bot_num", type=int, default=1)
    parser.add_argument("--log_level", type=str,
                        choices=["info", "debug"], default="info")
    args = parser.parse_args()

    swtich_bot_interval_sec = 5 * 60

    log_level = logging.INFO
    if args.log_level == "debug":
        log_level = logging.DEBUG

    logdir = os.path.join(LOG_DIR, datetime.now().strftime("%Y-%m-%d-%H-%M"))
    create_or_clean_folder(logdir)
    main_logger = create_logger("main",
                                log_file_path=os.path.join(logdir, 'main.log'),
                                log_level=log_level)

    try:
        sub_procs = []
        web_bots = []
        for idx in range(args.web_bot_num):
            web_bot = ChatGPTWebBot(
                chrome_user_data_dir=os.path.join(
                    WEB_DRIVER_DIR, "user_data_{}".format(idx)),
                logger=main_logger)
            web_bot.go_chat_page()
            web_bots.append(web_bot)

        input(("1. Make sure the ChatGPT page is loaded ready.\n"
               "2. Setup the live cast and make it going.\n"
               "Hit any key to continue"))

        for web_bot in web_bots:
            web_bot.prepare_chat_page()

        live_url_id = args.live_url_id
        if not live_url_id:
            # A real live broadcast
            live_url_id = input("Enter the live url ID: ")

        while True:
            wss_comm_queue = CommunicationQueue(maxsize=500)
            wss_p = multiprocessing.Process(target=wss_worker,
                                            args=(int(live_url_id),
                                                  wss_comm_queue,
                                                  os.path.join(
                                                  logdir, 'wss_worker.log'),
                                                  log_level))
            wss_p.start()
            time.sleep(3)
            ok = input(
                "Is wss client successfully connected?\nn = no & exit\nnr = no & retry\nother = yes & proceed: ")
            if ok == 'n':
                sub_procs.append(wss_p)
                raise RuntimeError("wss client not okay")
            elif ok == 'nr':
                wss_p.terminate()
                wss_p.join()
                wss_p.close()
                del wss_comm_queue
                main_logger.info("Restarting wss client ...")
                time.sleep(3)
            else:
                sub_procs.append(wss_p)
                break

        main_logger.info("sub procs pid: {}".format(
            [p.pid for p in sub_procs]))

        qs = QuestionSelector(wss_comm_queue,
                              logger=main_logger)

        start_time = int(time.time())

        iteration = 0
        while True:
            now = int(time.time())
            idx = iteration % len(web_bots)

            web_bot = web_bots[idx]
            main_logger.info("Using web_bot {} ...".format(idx))
            web_bot.bring_to_foreground()

            time.sleep(5)
            wss_comm_queue.clear()
            web_bot.set_count_down(time_interval=qs.collect_interval)

            q_text = qs.collect_and_select_question()
            if q_text:
                web_bot.send_question(q_text)
                web_bot.wait_answer(timeout_sec=120)
            iteration += 1

    finally:
        for p in sub_procs:
            p.terminate()
            p.join()
            p.close()


if __name__ == "__main__":
    main()
