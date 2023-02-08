import time
import _thread
from collections import OrderedDict
import random
import gzip
import re
import json
import urllib

import requests
import websocket
from google.protobuf import json_format

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


class DouyinLiveCracker(object):
    class QuestionsPool(object):
        def __init__(self, logger):
            self.logger = logger
            self.q_format = ''
            #self.q_format = '问题'
            self.questions = OrderedDict()

        def clear(self):
            self.questions.clear()

        def add_question(self, user_id, question):
            if question.startswith(self.q_format):
                question = question[2:]
                if question:
                    self.questions[user_id] = question
                    self.logger.debug(
                        "Added user_id: {}, question: {}".format(user_id, question))

        def checkout(self):
            return random.sample(list(self.questions.values(), k=1))

    def __init__(self, live_url_id, logger=None) -> None:
        if not logger:
            self.logger = create_logger("douyin_live_cracker")
        else:
            self.logger = logger

        self.live_url = "https://live.douyin.com/{}".format(live_url_id)
        self.user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
        self.live_req_header = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            # self.user_agent,
            'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36",
            'cookie': '__ac_nonce=0638733a400869171be51',
        }

        self.web_socket_url = ("wss://webcast3-ws-web-hl.douyin.com"
                               "/webcast/im/push/v2/?"
                               "app_name=douyin_web&version_code=180800"
                               "&webcast_sdk_version=1.3.0&update_version_code=1.3.0"
                               "&compress=gzip&internal_ext=internal_src:dim|wss_push_room_id:{}"
                               "|wss_push_did:{}"
                               "|dim_log_id:2022122306295965382308B5DCD45D07F8"
                               "|fetch_time:1671748199438|seq:1|wss_info:0-1671748199438-0-0"
                               "|wrds_kvs:WebcastRoomRankMessage-1671748147622091132_WebcastRoomStatsMessage-1671748195537766499"
                               "&cursor=t-1671748199438_r-1_d-1_u-1_h-1&"
                               "host=https://live.douyin.com&aid=6383&live_id=1&did_rule=3&debug=false&endpoint=live_pc"
                               "&support_wrds=1&im_path=/webcast/im/fetch/&device_platform=web"
                               "&cookie_enabled=true&screen_width=1440&screen_height=900"
                               "&browser_language=zh&browser_platform=MacIntel&browser_name=Mozilla&"
                               "browser_version=5.0%20(Macintosh;%20Intel%20Mac%20OS%20X%2010_15_7)%20AppleWebKit/537.36%20(KHTML,%20like%20Gecko)%20Chrome/108.0.0.0%20Safari/537.36"
                               "&browser_online=true&tz_name=Asia/Shanghai&identity=audience&room_id={}&heartbeatDuration=0")

        self.collect_event_timestamp = None
        self.questions_pool = self.__class__.QuestionsPool(self.logger)

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
            # self.user_agent,
            'user-agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
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
        decompressed = gzip.decompress(wssPackage.payload)
        payloadPackage = Response()
        payloadPackage.ParseFromString(decompressed)
        # 发送ack包
        if payloadPackage.needAck:
            self.sendAck(ws, logId, payloadPackage.internalExt)
        for msg in payloadPackage.messagesList:
            if msg.method == 'WebcastLikeMessage':
                pass
            elif msg.method == 'WebcastMemberMessage':
                pass
            elif msg.method == 'WebcastGiftMessage':
                pass
            elif msg.method == 'WebcastChatMessage':
                self.logger.info("New message")
                message = ChatMessage()
                message.ParseFromString(msg.payload)

                text = message.content
                user_id = message.user.shortId
                event_time = message.eventTime

                # if self.collect_event_time and event_time >= self.collect_event_time:
                self.questions_pool.add_question(user_id, text)

            if msg.method == 'WebcastSocialMessage':
                pass

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

    def start_collect(self):
        self.questions_pool.clear()
        self.collect_event_time = time.time()

    def stop_collect(self):
        self.collect_event_time = None

    def checkout_question(self):
        question = self.questions_pool.checkout()
        self.logger.info("Checked out question: {}".format(question))
        return question
