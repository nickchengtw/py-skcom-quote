
from datetime import datetime
import threading
from time import sleep
import pandas as pd
import re
from loguru import logger

from src.skcom_common import *
from src.kline import *


class OSQuote:
    def __init__(self, config_name, config, connection, ui) -> None:
        super().__init__()
        self.CONFIG_NAME = config_name
        self.CONFIG = config
        self.CONN = connection
        self._ui = ui
        
        self.connected = False

        self.kbar_buffer = []

        self.os_list_lock = threading.Lock()
        self.os_list_buffer = []
        
        self.historical_buffer = {}
        self.is_historical_end = {}
        self.kline_generators = {}

    @classmethod
    def get_os_kline_generator(cls, symbol):
        # if 'TWN' in symbol:
        #     return LiveKlineGenerator('', '5T', time(14, 45), time(8, 50), time(4, 45),
        #         (lambda t: time(8, 50) <= t.time() and t.time() <= time(13, 50))
        #         )
        # elif 'JNM' in symbol:
        #     return LiveKlineGenerator('', '5T', time(16, 30), time(8, 50), time(5),
        #         (lambda t: time(8, 50) <= t.time() and t.time() <= time(15, 15))
        #         )
        # elif 'CN' in symbol:
        #     return LiveKlineGenerator('', '5T', time(17), time(9, 5), time(5, 15),
        #         (lambda t: time(9, 5) <= t.time() and t.time() <= time(16, 35))
        #         )
        # elif 'HSI' in symbol:
        #     return LiveKlineGenerator('', '5T', time(17, 15), time(9, 20), time(3),
        #         (lambda t: time(9, 20) <= t.time() and t.time() <= time(16, 30))
        #         )
        
        # TODO Current strategy only need kline when TX is trading, but this is not a regular ay
        return LiveKlineGenerator('', '5T', time(15), time(8, 50), time(5), cls.kbar_time_valid)

    @staticmethod
    def kbar_time_valid(t):
        return (
            (time(8, 45) < t.time() and t.time() <= time(13, 45))
            or time(15) < t.time()
            or t.time() <= time(5)
        )

    @staticmethod
    def offset_time(td, kbars):
        return pd.DataFrame(
            kbars.to_numpy(),
            index=[i + td for i in kbars.index],
            columns=kbars.columns)

    @staticmethod
    def offset_timezone(symbol, kbars):
        if 'JNM' in symbol:
            return OSQuote.offset_time(-timedelta(hours=1), kbars)
        elif 'DXM' in symbol:
            return OSQuote.offset_time(timedelta(hours=7), kbars)
        elif 'NQ' in symbol:
            return OSQuote.offset_time(timedelta(hours=14), kbars)
        elif 'YM' in symbol:
            return OSQuote.offset_time(timedelta(hours=14), kbars)
        return kbars

    def change_state(self, state):
        logger.info(f'State: {state}')
        self._ui.on_state_change(state)

    def connect(self):
        handle_state_code('skOSQ.SKOSQuoteLib_EnterMonitor()', skOSQ.SKOSQuoteLib_EnterMonitor())
        for _ in range(20):
            if skOSQ.SKOSQuoteLib_IsConnected() == 1:
                self.connected = True
                break
            logger.info(f"wait os-connection complete")
            sleep(0.5)
        else:
            logger.critical("OS Connection not complete")

    def disconnect(self):
        handle_state_code('skOSQ.SKOSQuoteLib_LeaveMonitor()', skOSQ.SKOSQuoteLib_LeaveMonitor())
        self.connected = False

    def get_symbol_info(self, nIndex):
        pStock = sk.SKFOREIGN_9()
        skOSQ.SKOSQuoteLib_GetStockByIndexNineDigit(nIndex, pStock)
        return pStock.bstrStockNo, pStock.sDecimal

    def get_oversea_product(self):
        self.os_list_buffer = []
        self.os_list_lock.acquire()
        handle_state_code('skOSQ.SKOSQuoteLib_GetOverseaProducts()', skOSQ.SKOSQuoteLib_RequestOverseaProducts())
        self.os_list_lock.acquire()
        self.os_list_lock.release()
        return self.os_list_buffer

    def kline(self, symbol, start, end, am=0, timeframe=1):
        logger.info(f"KLINE: {symbol} am={am} timeframe={timeframe}")
        self.kbar_buffer = []
        handle_state_code(
            'SKOSQuoteLib_RequestKLineByDate',
            skOSQ.SKOSQuoteLib_RequestKLineByDate(symbol, 0, '19700101', end.strftime('%Y%m%d'), timeframe)
            )
        return pd.DataFrame(
            [row[1:] for row in self.kbar_buffer],
            index=[pd.Timestamp(datetime.strptime(row[0], '%Y/%m/%d %H:%M')) for row in self.kbar_buffer],
            columns=['Open', 'High', 'Low', 'Close', 'Volume']
        )

    def OnKLineData(self, bstrStockNo, bstrData):
        str_data = bstrData.split(", ")
        row = [str_data[0]] + [float(num) for num in str_data[1:]]
        self.kbar_buffer.append(row)

    def OnOverseaProducts(self, bstrValue):
        data = bstrValue.split(',')
        if re.match('^##', data[0]):
            self.os_list_lock.release()
        else:
            self.os_list_buffer.append(data)

    @logger.catch
    def OnConnect(self, nKind, nCode):
        if (nKind == 3001):
            logger.info("OS-Connection: Connected")
        elif (nKind == 3002):
            logger.info("OS-Connection: Disconnected!")
            self.change_state(QuoteState.DISCONNECTED)
        elif (nKind == 3003):
            logger.info("OS-Connection: Stocks ready!")
        elif (nKind == 3015):
            pass
        elif (nKind == 3021):
            self.connected = False
            logger.critical("OS-Connection: Error!")
            self.change_state(QuoteState.ERROR)

    @logger.catch
    def OnNotifyHistoryTicksNineDigit(self, nIndex, nPtr, nDate, nTime, nClose, nQty):
        # BUG disabled
        pass
        # symbol, float_s = self.get_symbol_info(nIndex)
        # traded_time = datetime.strptime(str(nDate) + str(nTime).zfill(6), '%Y%m%d%H%M%S')
        # price = nClose/(10**float_s)
        # self.historical_buffer[symbol].append([traded_time, price, nQty])

    @logger.catch
    def OnNotifyTicksNineDigit(self, nIndex, nPtr, nDate, nTime, nClose, nQty):
        symbol, float_s = self.get_symbol_info(nIndex)
        traded_time = datetime.strptime(str(nDate) + str(nTime).zfill(6), '%Y%m%d%H%M%S')
        price = nClose/(10**float_s)

        self.CONN.push_tick(symbol, {
            'time': traded_time,
            'price': price,
            'vol': nQty
        })

        # BUG disabled
        #
        # if not self.is_historical_end[symbol]:
        #     logger.info(f"{symbol} Historical buffer size={len(self.historical_buffer[symbol])}")
        #     if len(self.historical_buffer[symbol]) > 0:
        #         df = pd.DataFrame(
        #             [row[1:] for row in self.historical_buffer[symbol]],
        #             index=[pd.Timestamp(row[0]) for row in self.historical_buffer[symbol]],
        #             columns=['Price', 'Volume']
        #         )

        #         generator = self.kline_generators[symbol]
        #         # kbars_h1 = move_back_day(generator['H1'].on_ticks(time_align_day(df), td=True))
        #         # kbars_m15 = generator['M15'].on_ticks(df)
        #         kbars_m5 = self.offset_timezone(symbol, generator['M5'].on_ticks(df))
        #         # kbars_m1 = generator['M1'].on_ticks(df)

        #         # conn.kline_write_historical(symbol, 'H1', kbars_h1)
        #         # conn.kline_write_historical(symbol, 'M15', kbars_m15)
        #         conn.kline_write_historical(symbol, 'M5', kbars_m5)
        #         # conn.kline_write_historical(symbol, 'M1', kbars_m1)
        #     self.is_historical_end[symbol] = True

        df = pd.DataFrame(
            [[price, nQty]],
            index=[traded_time],
            columns=['Price', 'Volume']
        )
        generator = self.kline_generators[symbol]
        # kbars_h1 = move_back_day(generator['H1'].on_ticks(time_align_day(df), td=True))
        # kbars_m15 = generator['M15'].on_ticks(df)
        kbars_m5 = generator['M5'].on_ticks(self.offset_timezone(symbol, df))
        # kbars_m1 = generator['M1'].on_ticks(df)

        # for ts, _ in kbars_m1.iterrows():
        #     if ts in kbars_h1.index:
        #         conn.kline_add_new(symbol, 'H1', kbars_h1.loc[ts])
        #     if ts in kbars_m15.index:
        #         conn.kline_add_new(symbol, 'M15', kbars_m15.loc[ts])
        #     if ts in kbars_m5.index:
        #         conn.kline_add_new(symbol, 'M5', kbars_m5.loc[ts])
        #     conn.kline_add_new(symbol, 'M1', kbars_m1.loc[ts])
        for ts, _ in kbars_m5.iterrows():
            self.CONN.kline_add_new(symbol, 'M5', kbars_m5.loc[ts])

    @logger.catch
    def subscribe_oversea_market(self, symbol):
        logger.info(f"Subscribing {symbol}")
        item_symbol = symbol.split(',')[1]

        if not item_symbol in self.kline_generators:
            self.historical_buffer[item_symbol] = []
            self.is_historical_end[item_symbol] = False
            self.kline_generators[item_symbol] = {
                'M5': self.get_os_kline_generator(symbol)
            }
            # generator = self.kline_generators[item_symbol]
            # generator['M1'] = KBarGenerator(symbol, 'T')
            # generator['M5'] = self.get_os_kline_generator(symbol)
            # generator['M15'] = KBarGenerator(symbol, '15T')
            # generator['H1'] = KBarGenerator(symbol, '60T')

        # now = datetime.now()
        # kbars_m1 = quote.kline(symbol, now, now, am=am)
        # kbars_m5 = os_quote.kline(symbol, now, now, timeframe=5)
        # kbars_m15 = quote.kline(symbol, now, now, am=am, timeframe=15)
        # kbars_h1 = quote.kline(symbol, now, now, am=am, timeframe=60)
        # conn.kline_write_historical(symbol, 'H1', kbars_h1)
        # conn.kline_write_historical(symbol, 'M15', kbars_m15)
        # conn.kline_write_historical(item_symbol, 'M5', kbars_m5)
        # conn.kline_write_historical(symbol, 'M1', kbars_m1)

        _, n_code = skOSQ.SKOSQuoteLib_RequestTicks(-1, symbol)
        handle_state_code('SKOSQuoteLib_RequestTicks()', n_code)

        self._ui.on_symbol_subscribed(symbol)

    @logger.catch
    def quote(self):
        if self.CONFIG.get('osf_symbols'):
            logger.info("OverSea\n  " + '\n  '.join(self.CONFIG['osf_symbols']))
            products = self.get_oversea_product()
            for s in self.CONFIG['osf_symbols']:
                all_date = sorted([i for i in products if re.search(s + '\d{4}', i[2])], key=lambda i: i[4])
                if len(all_date) == 0:
                    continue
                closest = all_date[0]
                self.subscribe_oversea_market(closest[0] + ',' + closest[2])
                
            self.change_state(QuoteState.CONNECTED)

    def start(self):
        while True:
            now = datetime.now()
            if not self.is_trading_time(now) and self.connected:
                self.disconnect()
            if self.is_trading_time(now) and not self.connected:
                self.connect()
                sleep(5)
                self.quote()
            sleep(5)

    @staticmethod
    def is_trading_time(time_):
        return time(8, 35) <= time_.time() or time_.time() <= time(5)
