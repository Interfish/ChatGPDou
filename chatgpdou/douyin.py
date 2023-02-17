import time
import _thread
from collections import OrderedDict
import random
import gzip
import re
import json
import logging
import urllib

import requests
import websocket

from douyin_live.dy_pb2 import PushFrame
from douyin_live.dy_pb2 import Response
from douyin_live.dy_pb2 import MemberMessage
from douyin_live.dy_pb2 import GiftMessage
from douyin_live.dy_pb2 import ChatMessage
from douyin_live.dy_pb2 import SocialMessage
from douyin_live.dy_pb2 import RoomUserSeqMessage
from douyin_live.dy_pb2 import UpdateFanTicketMessage
from douyin_live.dy_pb2 import CommonTextMessage

from chatgpdou import create_logger


class QuestionSelector(object):
    def __init__(self, comm_queue, logger=None):
        if not logger:
            self.logger = create_logger("question_selector")
        else:
            self.logger = logger

        self.comm_queue = comm_queue
        #self.q_format = ''
        self.q_format = '提问'
        self.message_pool = []
        self.questions = OrderedDict()

        self.default_questions = [
            "什么是宇宙中最神秘的事物？",
            "如果你能拥有任何一个超能力，你会选择什么？",
            "在这个世界上，什么东西最让你感到惊奇？",
            "假如你能够和一个历史人物进行面对面的交流，你会选择谁？为什么？",
            "如果你有一百万美元，你会用它来做什么？",
            "什么是最好的书籍？为什么？",
            "你最喜欢的电影是哪一部？为什么？",
            "你认为人工智能能够取代人类吗？",
            "如果你能够设计一个机器人，你会让它具备哪些功能？",
            "你认为世界上最大的难题是什么？",
            "你认为自然界中最有趣的生物是什么？为什么？",
            "你认为宇宙中最有趣的行星是什么？为什么？",
            "你觉得哪个发明最改变了世界？",
            "如果你能够拥有一个超能力，你会选择什么？",
            "如果你能够穿越时间，你会选择去哪个年代？",
            "你认为最有趣的科学理论是什么？",
            "你最喜欢的食物是什么？为什么？",
            "你最喜欢的音乐类型是什么？",
            "你认为哪种技术能够改变世界？",
            "你认为自然界中最美的景色是什么？为什么？",
            "你认为未来最有可能会发生什么事情？",
            "如果你能够前往任何一个地方，你会去哪里？为什么？",
            "你最喜欢的运动是什么？",
            "你认为人类最伟大的成就是什么？",
            "你认为未来的交通方式会是什么样子？",
            "你认为人类最需要改变的习惯是什么？",
            "你认为哪个国家最有可能成为全球领导者？",
            "如果你能够拥有一个神秘的能力，你会选择什么？",
            "你最喜欢的艺术形式是什么？为什么？",
            "你认为未来的教育方式会是什么样子？",
        ]

    def collect_and_select_question(self, time_interval=15):
        self.start = time.time()
        self.logger.info("=================")
        self.logger.info(
            "Start collecting questions, timestamp {} ...".format(self.start))
        self.message_pool.clear()
        self.questions.clear()
        self.stop = self.start + time_interval
        while True:
            now = time.time()
            time_left = self.stop - now
            if time_left > 0:
                wss_pkg_payload = self.comm_queue.get_no_throw(True, time_left)
                if wss_pkg_payload is not None:
                    self.message_pool.append(wss_pkg_payload)
            else:
                break

        self.logger.info(
            "Stopped collecting questions, timestamp {}".format(self.stop))
        for wss_pkg_payload in self.message_pool:
            decompressed = gzip.decompress(wss_pkg_payload)
            payload_pkg = Response()
            payload_pkg.ParseFromString(decompressed)
            for msg in payload_pkg.messagesList:
                if msg.method == 'WebcastLikeMessage':
                    pass
                elif msg.method == 'WebcastMemberMessage':
                    pass
                elif msg.method == 'WebcastGiftMessage':
                    pass
                elif msg.method == 'WebcastChatMessage':
                    message = ChatMessage()
                    message.ParseFromString(msg.payload)
                    text = message.content
                    user_id = message.user.shortId
                    event_time = message.eventTime
                    self.logger.debug("msg: {}, uid: {}, timestamp: {}".format(
                        text, user_id, event_time))
                    if event_time >= self.start and event_time <= self.stop:
                        self.add_question(user_id, text, event_time)
                if msg.method == 'WebcastSocialMessage':
                    pass

        question = None
        if self.questions:
            question = self.checkout_question()
            self.logger.info("Selected question: {}".format(question))
        else:
            question = random.sample(self.default_questions, k=1)
            self.logger.info(
                "No question is selected, pick from default pool: {}".format(question))
        return question

    def add_question(self, user_id, question, event_time):
        if question.startswith(self.q_format):
            question = question[len(self.q_format):]
            if question:
                self.questions[user_id] = question

    def checkout_question(self):
        questions = list(self.questions.values())
        self.logger.info("questions:\n" + "\n".join(questions))
        question = random.sample(questions, k=1)
        self.logger.info("Checked out question: {}".format(question))
        return question


class DouyinLiveWebSocketServer(object):
    def __init__(self, live_url_id, comm_queue, log_path=None, log_level=logging.INFO) -> None:
        if not log_path:
            self.logger = create_logger(
                "douyin_live_web_socket_server", log_level=log_level)
        else:
            self.logger = create_logger(
                "douyin_live_web_socket_server", log_file_path=log_path, log_level=log_level)
        self.comm_queue = comm_queue

        self.live_url = "https://live.douyin.com/{}".format(live_url_id)
        self.user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
        self.live_req_header = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'User-Agent': self.user_agent,
            'cookie': '__ac_nonce=0638733a400869171be51',
        }

        # self.web_socket_url = ("wss://webcast3-ws-web-hl.douyin.com"
        #                       "/webcast/im/push/v2/?"
        #                       "app_name=douyin_web&version_code=180800"
        #                       "&webcast_sdk_version=1.3.0&update_version_code=1.3.0"
        #                       "&compress=gzip&internal_ext=internal_src:dim|wss_push_room_id:{}"
        #                       "|wss_push_did:{}"
        #                       "|dim_log_id:20230214220033B506EE3903790E3059C1"
        #                       "|fetch_time:1671748199438|seq:1|wss_info:0-1671748199438-0-0"
        #                       "|wrds_kvs:WebcastRoomRankMessage-1671748147622091132_WebcastRoomStatsMessage-1671748195537766499"
        #                       "&cursor=t-1671748199438_r-1_d-1_u-1_h-1&"
        #                       "host=https://live.douyin.com&aid=6383&live_id=1&did_rule=3&debug=false&endpoint=live_pc"
        #                       "&support_wrds=1&im_path=/webcast/im/fetch/&device_platform=web"
        #                       "&cookie_enabled=true&screen_width=1440&screen_height=900"
        #                       "&browser_language=zh&browser_platform=MacIntel&browser_name=Mozilla&"
        #                       "browser_version=5.0%20(Macintosh;%20Intel%20Mac%20OS%20X%2010_15_7)%20AppleWebKit/537.36%20(KHTML,%20like%20Gecko)%20Chrome/108.0.0.0%20Safari/537.36"
        #                       "&browser_online=true&tz_name=Asia/Shanghai&identity=audience&room_id={}&heartbeatDuration=0")

        self.web_socket_url = "wss://webcast3-ws-web-hl.douyin.com/webcast/im/push/v2/?app_name=douyin_web&version_code=180800&webcast_sdk_version=1.3.0&update_version_code=1.3.0&compress=gzip&internal_ext=internal_src:dim|wss_push_room_id:{}|wss_push_did:{}|dim_log_id:20230214220033B506EE3903790E3059C1|fetch_time:1676383233624|seq:1|wss_info:0-1676383233624-0-0|wrds_kvs:WebcastRoomRankMessage-1676382424986905036_WebcastRoomStatsMessage-1676383228980195548&cursor=d-1_u-1_h-1_t-1676383233624_r-1&host=https://live.douyin.com&aid=6383&live_id=1&did_rule=3&debug=false&endpoint=live_pc&support_wrds=1&im_path=/webcast/im/fetch/&user_unique_id=7179057636167058979&device_platform=web&cookie_enabled=true&screen_width=1440&screen_height=900&browser_language=en&browser_platform=MacIntel&browser_name=Mozilla&browser_version=5.0%20(Macintosh;%20Intel%20Mac%20OS%20X%2010_15_7)%20AppleWebKit/537.36%20(KHTML,%20like%20Gecko)%20Chrome/110.0.0.0%20Safari/537.36&browser_online=true&tz_name=Asia/Shanghai&identity=audience&room_id={}&heartbeatDuration=0&signature=WgK6lxlg8whoRwCL"

    def run_forever(self):
        self.logger.info("Connecting to {}".format(self.live_url))

        res = requests.get(url=self.live_url, headers=self.live_req_header)
        data = res.cookies.get_dict()
        self.ttwid = data['ttwid']
        res = res.text
        res = re.search(
            r'<script id="RENDER_DATA" type="application/json">(.*?)</script>', res)
        res = res.group(1)
        res = urllib.parse.unquote(res, encoding='utf-8', errors='replace')
        res = json.loads(res)
        self.live_room_id = res['app']['initialState']['roomStore']['roomInfo']['roomId']
        self.logger.info("live_room_id: {}, ttwid {}".format(
            self.live_room_id, self.ttwid))

        self.web_socket_url = self.web_socket_url.format(
            self.live_room_id, self.live_room_id, self.live_room_id)

        websocket.enableTrace(False)
        self.ws_header = {
            'cookie': "ttwid={}".format(self.ttwid),
            'user-agent': self.user_agent
        }
        self.logger.info("Connecting to wss {}".format(self.web_socket_url))

        self.ws_app = websocket.WebSocketApp(
            self.web_socket_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            header=self.ws_header
        )
        self.ws_app.run_forever()

    def sendAck(self, ws, logId, internalExt):
        obj = PushFrame()
        obj.payloadType = 'ack'
        obj.logId = logId
        obj.payloadType = internalExt
        data = obj.SerializeToString()
        ws.send(data, websocket.ABNF.OPCODE_BINARY)

    def on_message(self, ws: websocket.WebSocketApp, message: bytes):
        self.logger.debug(
            "Recieved new packages {} bytes".format(len(message)))
        wssPackage = PushFrame()
        wssPackage.ParseFromString(message)
        logId = wssPackage.logId

        self.comm_queue.put(wssPackage.payload)

        decompressed = gzip.decompress(wssPackage.payload)
        payloadPackage = Response()
        payloadPackage.ParseFromString(decompressed)
        # 发送ack包
        if payloadPackage.needAck:
            self.sendAck(ws, logId, payloadPackage.internalExt)

    def ping(self, ws):
        while True:
            obj = PushFrame()
            obj.payloadType = 'hb'
            data = obj.SerializeToString()
            ws.send(data, websocket.ABNF.OPCODE_BINARY)
            time.sleep(10)

    def on_open(self, ws):
        _thread.start_new_thread(self.ping, (ws,))

    def on_error(self, ws, error):
        self.logger.error("websocket error: {}".format(str(error)))

    def on_close(self, ws, a, b):
        self.logger.error("websocket closing ...")
