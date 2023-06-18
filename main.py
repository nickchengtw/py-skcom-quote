import threading
from loguru import logger
import comtypes.client
import argparse
import yaml
from line_notify import LineNotify
from tkinter import Tk, messagebox

from src.skcom_common import *
from src.connection import *
from src.win import FrameLogin
from src.tw_quote import *
from src.os_quote import *
from src.recorder import DataRecorder


class QuoteUI:
    def __init__(self, config_name, notify_token=None, win=None) -> None:
        self._config_name = config_name
        self.line_notify = LineNotify(notify_token)
        self._win = win

        self.requested_market = []
        self.failed_market = []

    def notify_send(self, text):
        logger.info(f"Sending message: {text}")
        self.line_notify.send(text)

    def on_subscribe_success(self, symbol):
        self._win.add_symbol(symbol)
        self.requested_market.append(symbol)

    def on_subscribe_failed(self, symbol):
        self.requested_market.append(symbol)
        self.failed_market.append(symbol)

    def on_state_change(self, state):
        if state == QuoteState.DISCONNECTED:
            self.notify_send("SKCOM 斷線")
            self._win.change_status("disconnected", "red")
        elif state == QuoteState.ERROR:
            self.notify_send("SKCOM 連線異常!!!")
            self._win.change_status("ERROR!!!", "red")
        elif state == QuoteState.CONNECTED:
            self.notify_send(f"SKCOM-{self._config_name} 啟動完成")
            self._win.change_status("Listening", "green")

            self.notify_send(
                (
                    f"{self._config_name}\n"
                    f"索取{len(self.requested_market)}項商品\n"
                    f"{len(self.failed_market)}項無法取得"
                )
            )


class OSQuoteUI(QuoteUI):
    def on_state_change(self, state):
        if state == QuoteState.DISCONNECTED:
            self.notify_send("OS 斷線")
            self._win.os_change_status("disconnected", "red")
        elif state == QuoteState.ERROR:
            self.notify_send("OS 連線異常!!!")
            self._win.os_change_status("ERROR!!!", "red")
        elif state == QuoteState.CONNECTED:
            self.notify_send(f"OS-{self._config_name} 啟動成功")
            self._win.os_change_status("Listening", "green")

    def on_symbol_subscribed(self, symbol):
        self._win.add_symbol(symbol)


def start_quote(config):
    logger.info("USER: " + config["luser"])
    try:
        api_login(config["luser"], config["lpass"])
    except SkcomError as err:
        logger.critical(f"Account error {err}")
        messagebox.showerror(message="Login failed")
        os._exit(1)

    if config.get("oversea"):
        os_quote.start()
    else:
        quote.start()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config_name")
    parser.add_argument("port_number")
    parser.add_argument(
        "--msg", metavar="token", type=str, help="Send message to channel"
    )
    args, _ = parser.parse_known_args()

    NOTIFY_TOKEN = args.msg
    SERVER_PORT_NUMBER = args.port_number
    CONFIG_NAME = args.config_name
    CONN_CONFIG = yaml.load(
        open(os.path.split(os.path.realpath(__file__))[0] + "\\conn.yaml", "r"),
        Loader=yaml.CLoader,
    )
    CONFIG = CONN_CONFIG[CONFIG_NAME]

    skC.SKCenterLib_SetLogPath("logs\\CapitalLog" + f"_{CONFIG_NAME}")
    skC.SKCenterLib_Debug(True)

    log_path = f"logs/skcom_{CONFIG_NAME}.log"
    logger.add(log_path, backtrace=True, diagnose=True, level="DEBUG")

    logger.info("==========")
    logger.info("Starting quote")
    logger.info("==========")

    logger.info(f"Connect to TWQuoteManager, port {SERVER_PORT_NUMBER}")
    conn = Connection(SERVER_PORT_NUMBER)

    root = Tk()
    root.title(f"Connection {CONFIG_NAME}")
    win = FrameLogin(master=root)

    ui = QuoteUI(CONFIG_NAME, notify_token=NOTIFY_TOKEN, win=win)
    os_ui = OSQuoteUI(CONFIG_NAME, notify_token=NOTIFY_TOKEN, win=win)

    tick_dir = "logs\\Ticks\\"
    data_recorder = DataRecorder(tick_dir)
    if not os.path.exists(tick_dir):
        os.makedirs(tick_dir)

    global quote
    global os_quote
    quote = TWQuote(CONFIG_NAME, CONFIG, conn, ui)
    os_quote = OSQuote(CONFIG_NAME, CONFIG, conn, os_ui)
    sk_reply = SKReply()

    quote.on_state_change += ui.on_state_change
    quote.on_subscribe_success += ui.on_subscribe_success
    quote.on_subscribe_failed += ui.on_subscribe_failed
    quote.on_tick += data_recorder.write_tick

    SKQuoteLibEventHandler = comtypes.client.GetEvents(skQ, quote)
    SKOSQuoteLibEventHandler = comtypes.client.GetEvents(skOSQ, os_quote)
    SKReplyLibEventHandler = comtypes.client.GetEvents(skR, sk_reply)
    threading.Thread(target=start_quote, args=(CONFIG,)).start()

    # root.withdraw()
    root.mainloop()


if __name__ == "__main__":
    main()
