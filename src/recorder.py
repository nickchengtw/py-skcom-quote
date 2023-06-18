
import os
import queue
import threading

from loguru import logger

class DataRecorder:
    def __init__(self, root_dir) -> None:
        self.root_dir = root_dir
        
        self.tick_queue = queue.Queue()

        threading.Thread(target=self._write_to_file).start()

    def write_tick(self, symbol, traded_time, price, bid, ask, nQty):
        self.tick_queue.put((symbol, traded_time, price, bid, ask, nQty))

    @logger.catch
    def _write_to_file(self):
        logger.info(f'Start recording data, root_dir={self.root_dir}')
        while True:
            data = self.tick_queue.get()
            symbol = data[0]
            path = os.path.join(self.root_dir, f'{symbol}.txt')
            append_tuple_to_file(path, data[1:])


def append_tuple_to_file(file_path, new_tuple):
    with open(file_path, 'a') as file:
        file.write(','.join(str(x) for x in new_tuple) + '\n')

