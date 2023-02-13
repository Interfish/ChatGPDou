import os
import time

#from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException
from undetected_chromedriver import Chrome, ChromeOptions

from chatgpdou import create_logger
from chatgpdou import LOG_DIR, WEB_DRIVER_DIR
from chatgpdou import random_delay

env = dict(os.environ)
env['PATH'] = os.path.abspath(WEB_DRIVER_DIR) + os.pathsep + env['PATH']
os.environ.update(env)


class ChatGPTWebBot(object):
    def __init__(self,
                 chrome_user_data_dir=None,
                 chrome_profile_directory=None,
                 logger=None) -> None:
        self.chatgpt_url = "https://chat.openai.com/chat"
        self.add_hint_board_js = """
const mainElem = document.getElementsByTagName('main')[0];

var hintBoard = document.createElement('div');
hintBoard.style.position = "absolute";
hintBoard.style.top = "0";
hintBoard.style.left = "0";
hintBoard.style.width = "100%";
hintBoard.style.backgroundColor = "#444654";
hintBoard.style.borderBottom = "5px solid gray";

var hint = document.createElement("div");
hint.style.color = "white"
hint.style.display = "block";
hint.style.clear = "both";
hint.style.margin = "10px";
hint.style.textAlign = "center";
hint.innerHTML = "互动玩法: 倒计时期间，发送评论内容，输入格式为: 提问 问题内容。<br>倒计时结束，系统会自动抽取一个问题并向 ChatGPT 提问。<br>互动评论举例: 提问ChatGPT是什么?"
hintBoard.appendChild(hint);

var countdown = document.createElement("div");
countdown.id = "chatgpdou_hint_board_countdown";
countdown.style.display = "block";
countdown.style.margin = "10px";
countdown.style.textAlign = "center";
countdown.style.clear = "both";
countdown.style.color = "red";
countdown.innerHTML = "倒计时在本轮提问结束后自动开始";
hintBoard.appendChild(countdown);

mainElem.appendChild(hintBoard);
        """

        self.count_down_js = """
const countdown = document.getElementById("chatgpdou_hint_board_countdown");
var count = {0};
var set = setInterval(function() {{
    count--;
    countdown.innerHTML = "请在" + String(count) + "秒内输入提问";
    if (count <= 0) {{
      clearInterval(set);
      countdown.innerHTML = "倒计时在本轮提问结束后自动开始";
    }}
}}, 1000);
"""

        if not logger:
            self.logger = create_logger("chatgpt_web_bot")
        else:
            self.logger = logger
        self.default_wait = 40
        self.driver = None
        self.driver_options = ChromeOptions()
        self.logger.info(
            "chrome_user_data_dir: {}".format(chrome_user_data_dir))
        #self.logger.info("chrome_profile_directory: {}".format(chrome_profile_directory))
        if chrome_user_data_dir:
            self.driver_options.user_data_dir = os.path.abspath(
                chrome_user_data_dir)
        # self.driver_options.add_argument(
        #     "--user-data-dir={}".format(os.path.abspath(chrome_user_data_dir)))

        # if chrome_profile_directory:
            # self.driver_options.add_argument(
            #     "--profile-directory={}".format(chrome_profile_directory))
        self.reinitialize_driver()

    def reinitialize_driver(self):
        if self.driver is not None:
            self.driver.quit()
            delattr(self, "driver")
            random_delay(120, 130)
        random_delay(4, 5)
        self.driver = Chrome(options=self.driver_options)
        # bring the browser to foreground by screenshot
        self.driver.save_screenshot(os.path.join(LOG_DIR, "tmp.png"))

    def prepare_chat_page(self):
        self.driver.get(self.chatgpt_url)
        self.logger.info("==============================")
        input("Hit any key if chat page is loaded ready: ")
        # Add hint board html onto this page.
        self.driver.execute_script(self.add_hint_board_js)
        # Find input textarea and click button
        self.text_area = self.driver.find_element(By.XPATH,
                                                  "//main//form//textarea")
        self.send_button = self.driver.find_element(By.XPATH,
                                                    "//main//form//button[contains(@class, 'absolute')]")

    def set_count_down(self, time_interval=15):
        self.driver.execute_script(self.count_down_js.format(time_interval))

    def wait_answer(self, timeout_sec=60):
        self.driver.implicitly_wait(10)
        try:
            self.driver.find_element(
                By.XPATH, "//div[contains(@class, 'result-streaming')]")
        except NoSuchElementException:
            self.driver.implicitly_wait(self.default_wait)
            return False
        self.logger.info("ChatGPT start streaming answer...")

        self.driver.implicitly_wait(0)
        start = time.time()
        while True:
            time.sleep(3)
            if time.time() - start > timeout_sec:
                try:
                    stop_button = self.driver.find_element(By.XPATH,
                                                           "//main//form//button[contains(@class, 'btn')]")
                    stop_button.click()
                    self.logger.warning("Click stop button error, plz check")
                except:
                    pass
                self.driver.implicitly_wait(self.default_wait)
                return False
            try:
                self.driver.find_element(
                    By.XPATH, "//div[contains(@class, 'result-streaming')]")
            except NoSuchElementException:
                break
        self.driver.implicitly_wait(self.default_wait)
        self.logger.info("Answering complete")
        return True

    def send_question(self, q_text):
        # clear
        self.text_area.send_keys(Keys.CONTROL + "a")
        self.text_area.send_keys(Keys.DELETE)
        # input text
        self.text_area.send_keys(q_text)
        time.sleep(2)
        self.send_button.click()
        self.logger.info("Sent question: {}".format(q_text))

        # div result-streaming markdown prose w-full break-words dark:prose-invert light
