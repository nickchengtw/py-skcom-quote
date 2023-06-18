
import zmq
import threading
import queue
from loguru import logger

_context = zmq.Context()

class Connection():
    def __init__(self, port) -> None:
        self._socket = _context.socket(zmq.REQ)
        self._socket.connect(f"tcp://localhost:{port}")
        self._queue = queue.Queue()
        threading.Thread(target=self._sender).start()

    def _sender(self):
        while True:
            self._socket.send_pyobj(self._queue.get())
            self._socket.recv()

    def add_symbol(self, symbol):
        pass

    def kline_write_historical(self, symbol, timeframe, kbars):
        self._queue.put({
            'type': 'HIST',
            'symbol': symbol,
            'timeframe': timeframe,
            'kline': kbars
        })

    def kline_add_new(self, symbol, timeframe, kbar):
        self._queue.put({
            'type': 'LIVE',
            'symbol': symbol,
            'timeframe': timeframe,
            'kbar': kbar
        })

    def push_historical_tick(self, symbol, tick):
        self._queue.put({
            'type': 'HIST_TICK',
            'symbol': symbol,
            'tick': tick
        })

    def push_tick(self, symbol, tick):
        self._queue.put({
            'type': 'TICK',
            'symbol': symbol,
            'tick': tick
        })

    def push_trade_info(self, symbol, info):
        self._queue.put({
            'type': 'TINFO',
            'symbol': symbol,
            'trade_info': info
        })
