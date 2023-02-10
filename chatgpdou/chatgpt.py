import os
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException

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

        if not logger:
            self.logger = create_logger("chatgpt_web_bot")
        else:
            self.logger = logger
        self.default_wait = 20
        self.driver = None
        self.driver_options = webdriver.ChromeOptions()
        self.logger.info("chrome_user_data_dir: {}".format(chrome_user_data_dir))
        self.logger.info("chrome_profile_directory: {}".format(chrome_profile_directory))
        if chrome_user_data_dir:
            self.driver_options.add_argument(
                "--user-data-dir={}".format(os.path.abspath(chrome_user_data_dir)))
        if chrome_profile_directory:
            self.driver_options.add_argument(
                "--profile-directory={}".format(chrome_profile_directory))
        self.reinitialize_driver()

    def reinitialize_driver(self):
        if self.driver is not None:
            self.driver.quit()
            delattr(self, "driver")
            random_delay(120, 130)
        random_delay(4, 5)
        self.driver = webdriver.Chrome(chrome_options=self.driver_options)
        # bring the browser to foreground by screenshot
        self.driver.save_screenshot(os.path.join(LOG_DIR, "tmp.png"))

    def prepare_chat_page(self):
        self.driver.get(self.chatgpt_url)
        self.logger.info("==============================")
        input("Hit any key if chat page is loaded ready: ")
        # TBD update hint html onto this page.
        # Find input textarea and click button
        self.text_area = self.driver.find_element(By.XPATH,
                                                  "//main//form//textarea")
        self.send_button = self.driver.find_element(By.XPATH,
                                                    "//main//form//button[contains(@class, 'absolute')]")

    def set_count_down(self, time_interval=15):
        pass

    def wait_answer(self, timeout_sec=60):
        self.driver.implicitly_wait(10)
        try:
            self.driver.find_element(
                By.XPATH, "//div[contains(@class, 'result-streaming')]")
        except NoSuchElementException:
            self.driver.implicitly_wait(self.default_wait)
            return False

        self.driver.implicitly_wait(0)
        stop_button = self.driver.find_element(By.XPATH,
                                               "//main//form//button[containes(@class, 'btn')]")
        start = time.time()
        while True:
            time.sleep(3)
            if time.time() - start > timeout_sec:
                self.driver.implicitly_wait(self.default_wait)
                stop_button.click()
                return False
            try:
                self.driver.find_element(
                    By.XPATH, "//div[contains(@class, 'result-streaming')]")
            except NoSuchElementException:
                break
        return True

    def send_question(self, q_text):
        # clear
        self.text_area.sendKeys(Keys.CONTROL + "a")
        self.text_area.sendKeys(Keys.DELETE)
        # input text
        self.text_area.sendKeys(q_text)
        time.sleep(2)
        self.send_button.click()

        # div result-streaming markdown prose w-full break-words dark:prose-invert light
