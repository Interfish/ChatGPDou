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


def web_bot_worker(method_queue, ret_queue, chrome_user_data_dir, log_path, log_level):
    web_bot = ChatGPTWebBot(method_queue,
                            ret_queue,
                            chrome_user_data_dir=chrome_user_data_dir,
                            log_path=log_path,
                            log_level=log_level)
    web_bot.listen_method()


def send_method(method_queue, method, args=tuple(), kwargs={}):
    method_queue.put((method, args, kwargs))


def main():
    parser = argparse.ArgumentParser(description='ChatGPDou')
    parser.add_argument("live_url_id", nargs='?')
    parser.add_argument("--web_bot_num", type=int, default=1)
    parser.add_argument("--log_level", type=str,
                        choices=["info", "debug"], default="info")
    args = parser.parse_args()

    swtich_bot_interval_sec = 10 * 60

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
        web_bot_method_queues = [CommunicationQueue(
            maxsize=500) for _ in range(args.web_bot_num)]
        web_bot_ret_queues = [CommunicationQueue(
            maxsize=500) for _ in range(args.web_bot_num)]

        for idx, _ in enumerate(web_bot_method_queues):
            p = multiprocessing.Process(target=web_bot_worker,
                                        args=(web_bot_method_queues[idx],
                                              web_bot_ret_queues[idx],
                                              os.path.join(
                                                  WEB_DRIVER_DIR, "user_data_{}".format(idx)),
                                              os.path.join(
                                                  logdir, "web_bot_{}.log".format(idx)),
                                              log_level))
            p.start()
            sub_procs.append(p)

        for method_queue in web_bot_method_queues:
            send_method(method_queue, "go_chat_page")
            send_method(method_queue, "prepare_chat_page")

        input(("1. Make sure the ChatGPT page is prepared ready.\n"
               "2. Setup the live cast and make it going.\n"
               "Hit any key to continue"))

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
            time.wait(3)
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
        while True:
            now = int(time.time())
            idx = ((now - start_time) //
                   swtich_bot_interval_sec) % len(web_bot_method_queues)
            method_queue = web_bot_method_queues[idx]
            ret_queue = web_bot_ret_queues[idx]
            send_method(method_queue, "bring_to_foreground")

            time.sleep(5)
            wss_comm_queue.clear()
            send_method(method_queue, "set_count_down",
                        kwargs={"time_interval": 20})

            q_text = qs.collect_and_select_question(time_interval=20)
            if q_text:
                send_method(method_queue, "send_question", args=(q_text,))
                timeout_sec = 60
                send_method(method_queue, "wait_answer",
                            kwargs={"timeout_sec": timeout_sec})
                ret_queue.get_no_throw(True, timeout_sec=timeout_sec + 10)
            method_queue.clear()
            ret_queue.clear()

    finally:
        for p in sub_procs:
            p.terminate()
            p.join()
            p.close()


if __name__ == "__main__":
    main()
