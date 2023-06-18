
from datetime import datetime, time, timedelta
import threading
from time import sleep
import pandas as pd
import re
from loguru import logger
import eventkit as ev

from src.kline_manager import KlineManager
from src.trade_info import *
from src.skcom_common import *


class TWQuote:
    on_state_change = ev.Event()
    on_subscribe_success = ev.Event()
    on_subscribe_failed = ev.Event()
    
    on_tick = ev.Event()
    
    def __init__(self, config_name, config, connection, ui) -> None:
        super().__init__()
        self.CONFIG_NAME = config_name
        self.CONFIG = config
        self.CONN = connection
        
        self.state = QuoteState.DISCONNECTED
        self.requested_market = []
        self.failed_market = []

        self.kbar_buffer = []

        self.stock_list_lock = threading.Lock()
        self.stock_list_buffer = []

        self.opt_list_lock = threading.Lock()
        self.opt_list_buffer = []
        
        self.hist_kline_loaded = set()
        self.kline_manager = KlineManager(connection)
        
        self.trade_info_processor = None

    @staticmethod
    def op_closest_product(opt_products):
        last_week_product = sorted([i[6] for i in opt_products])[0]
        logger.info(f"Last week product is {last_week_product}")
        return [opt_data for opt_data in opt_products if opt_data[6] == last_week_product]

    @staticmethod
    def is_option_symbol(symbol):
        return re.match('TX\d{6}[A-Z]\d', symbol) or re.match('TXO\d{5}[A-Z]\d', symbol)

    def start(self):
        while True:
            now = datetime.now()
            if not self.is_trading_time(now) and self.state == QuoteState.CONNECTED:
                self.disconnect()
            if self.is_trading_time(now) and self.state == QuoteState.DISCONNECTED:
                self.quote()
            sleep(5)

    @staticmethod
    def is_trading_time(time_):
        return time(8, 35) <= time_.time() or time_.time() <= time(5)

    def quote(self):
        self.connect_until_success()
        self.securities_quote()
        self.futures_quote()
        self.futures_info_quote()
        self.option_quote()
        self.change_state(QuoteState.CONNECTED)

    def connect_until_success(self):
        while True:
            try:
                logger.info("Connecting")
                self.connect()
                break
            except:
                self.disconnect()
                logger.warning("Connect failed, retry")
                sleep(30)

    def connect(self):
        handle_state_code('SKQuoteLib_EnterMonitor', skQ.SKQuoteLib_EnterMonitor())
        for _ in range(50):
            if skQ.SKQuoteLib_IsConnected() != 2:
                break
            sleep(0.5)
        else:
            raise SkcomError("Unable to connect")

    def disconnect(self):
        handle_state_code('skQ.SKQuoteLib_LeaveMonitor()', skQ.SKQuoteLib_LeaveMonitor())

    def change_state(self, state):
        self.state = state
        logger.info(f'State: {self.state}')
        self.on_state_change.emit(state)

    @logger.catch
    def securities_quote(self):
        for s in self.CONFIG.get('ts_symbol', []):
            self.subscribe_market(MarketType.SECURITIES, s)

    @logger.catch
    def futures_quote(self):
        for s in self.CONFIG.get('mfix', []):
            self.subscribe_market(MarketType.FUTURES, s)

    @logger.catch
    def futures_info_quote(self):
        if self.CONFIG.get('future_info'):
            future_list = self.get_future_list_safe()
            tx_futures = [f.split(',') for f in future_list[0]]
            for symbol in [tx_futures[1][0], tx_futures[2][0]]:
                logger.info(f"Future info: {symbol}")
                assert re.match('^TX', symbol)
                self.subscribe_tinfo(symbol)

    def subscribe_tinfo(self, symbol):
        skQ.SKQuoteLib_RequestFutureTradeInfo(comtypes.automation.c_short(0), symbol)

    @logger.catch
    def option_quote(self):
        opt_data = self.get_opt_data_safe()
        tx_symbols = [opt_data for opt_data in opt_data if re.match('TX\\d', opt_data[0]) and not re.search('AM', opt_data[2])]
        txo_symbols = [opt_data for opt_data in opt_data if re.match('TXO', opt_data[0]) and not re.search('AM', opt_data[2])]
        logger.info(f"Week product len={len(tx_symbols)}")
        logger.info(f"Month product len={len(txo_symbols)}")
        last_week_symbols = self.op_closest_product(tx_symbols + txo_symbols)
        if last_week_symbols[0][0] == 'TXO':
            call_selected = [i[2] for i in last_week_symbols[self.CONFIG['sopclp']:self.CONFIG['sopcrp']]]
            put_selected = [i[3] for i in last_week_symbols[self.CONFIG['sopplp']:self.CONFIG['sopprp']]]
        else:
            call_selected = [i[2] for i in last_week_symbols[self.CONFIG['opclp']:self.CONFIG['opcrp']]]
            put_selected = [i[3] for i in last_week_symbols[self.CONFIG['opplp']:self.CONFIG['opprp']]]
        logger.info("CALL\n  " + '\n  '.join(call_selected))
        logger.info("PUT\n  " + '\n  '.join(put_selected))
        for i in call_selected:
            self.subscribe_market(MarketType.OPTIONS, i)
        for i in put_selected:
            self.subscribe_market(MarketType.OPTIONS, i)

    @logger.catch
    def subscribe_market(self, market_type, symbol):
        logger.info(f"Subscribing {symbol}")
        self.requested_market.append(symbol)
        try:
            self.kline_manager.init_symbol(market_type, symbol)
            if not (symbol in self.kline_manager.hist_kline_loaded):
                self.load_kline(symbol)
                self.kline_manager.hist_kline_loaded.add(symbol)
            self.request_ticks(symbol)
            self.on_subscribe_success.emit(symbol)
        except:
            self.on_subscribe_failed.emit(symbol)
            raise

    def load_kline(self, symbol):
        """
        WARNING
        Kline broke on first few kbar when timeframe=60
        """
        kbars_m1 = self.kline(symbol, 1)
        kbars_m5 = self.kline(symbol, 5)

        # TODO Special case for TX, refactor in future
        if symbol == 'TX00':
            now = datetime.now()
            kbars_m5 = self.kline_by_date(
                symbol, 
                (now - timedelta(days=1095)), now, 5)

        kbars_m15 = self.kline(symbol, 15)
        kbars_m30 = self.kline(symbol, 30)
        kbars_h1 = self.kline(symbol, 60)
        self.CONN.kline_write_historical(symbol, 'H1', kbars_h1)
        self.CONN.kline_write_historical(symbol, 'M30', kbars_m30)
        self.CONN.kline_write_historical(symbol, 'M15', kbars_m15)
        self.CONN.kline_write_historical(symbol, 'M5', kbars_m5)
        self.CONN.kline_write_historical(symbol, 'M1', kbars_m1)

    def get_future_list_safe(self):
        data1 = self.get_future_list()
        logger.info(f"Futures-List-1 len: {len(data1)}")
        sleep(5)
        data2 = self.get_future_list()
        logger.info(f"Futures-List-2 len: {len(data2)}")
        if len(data1) != len(data2):
            logger.warning("Futures-List data not complete retry")
            sleep(5)
            return self.get_future_list_safe()
        return data2

    def get_future_list(self):
        self.stock_list_buffer = []
        self.stock_list_lock.acquire()
        handle_state_code('skQ.SKQuoteLib_RequestStockList()', skQ.SKQuoteLib_RequestStockList(2))
        self.stock_list_lock.acquire()
        self.stock_list_lock.release()
        return self.stock_list_buffer

    def get_opt_data_safe(self):
        data1 = self.get_opt_data()
        logger.info(f"OPT-Data-1 len: {len(data1)}")
        sleep(5)
        data2 = self.get_opt_data()
        logger.info(f"OPT-Data-2 len: {len(data2)}")
        if len(data1) != len(data2):
            logger.warning("OPT-Data data not complete retry")
            sleep(5)
            return self.get_opt_data_safe()
        return data2

    def get_opt_data(self):
        self.opt_list_buffer = []
        self.opt_list_lock.acquire()
        handle_state_code('skQ.SKQuoteLib_GetStrikePrices()', skQ.SKQuoteLib_GetStrikePrices())
        self.opt_list_lock.acquire()
        self.opt_list_lock.release()
        return self.opt_list_buffer

    def kline(self, symbol, timeframe, count=1140, am=0):
        while True:
            try:
                raw_kbar = self.get_raw_kline(
                    symbol, datetime(1970, 1, 1), datetime.now(),
                    timeframe, am)[-count:]
                return self.parse_kline(raw_kbar)
            except:
                logger.warning("Can't parse kline, requesting new")

    def kline_by_date(self, symbol, time_start, time_end, timeframe, am=0):
        logger.info(f"Start downloading from {time_start} ~ {time_end}")
        kline = self.kline_by_date_batch(symbol, time_start, time_end, timeframe, am=am)
        time_end = kline.index[0]
        logger.info(f'Chunk from {kline.index[0]} ~ {kline.index[-1]}')
        
        while time_start < kline.index[0]:
            chunk = self.kline_by_date_batch(symbol, time_start, time_end, timeframe, am=am)
            chunk = chunk[chunk.index < kline.index[0]]
            
            if len(chunk) == 0:
                logger.info(f"No more data")
                break

            kline = pd.concat([chunk, kline])
            time_end = kline.index[0]
            logger.info(f'Chunk from {chunk.index[0]} ~ {chunk.index[-1]}')
        return kline

    def kline_by_date_batch(self, symbol, start, end, timeframe, am=0):
        while True:
            try:
                raw_kbar = self.get_raw_kline(
                    symbol, (end - timedelta(days=60)), end,
                    timeframe, am=am)
                return self.parse_kline(raw_kbar)
            except:
                logger.warning("Can't parse kline, requesting new")

    def get_raw_kline(self, symbol, start, end, timeframe, am=0):
        self.kbar_buffer = []
        m_nCode = skQ.SKQuoteLib_RequestKLineAMByDate(
            symbol, 0, 1, am,
            start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), timeframe)
        handle_state_code('SKQuoteLib_RequestKLineAMByDate', m_nCode)
        return self.kbar_buffer

    @staticmethod
    def parse_kline(raw_kbar):
        return pd.DataFrame(
            [row[1:] for row in raw_kbar],
            index=[pd.Timestamp(datetime.strptime(row[0], '%Y/%m/%d %H:%M')) for row in raw_kbar],
            columns=['Open', 'High', 'Low', 'Close', 'Volume']
        )

    def request_ticks(self, symbol):
        _, stat_code = skQ.SKQuoteLib_RequestTicks(-1, symbol)
        handle_state_code('SKQuoteLib_RequestTicks', stat_code)

    def get_symbol(self, sMarketNo, nStockidx):
        pStock = sk.SKSTOCK()
        _, state_code = skQ.SKQuoteLib_GetStockByIndex(sMarketNo, nStockidx, pStock)
        if state_code != 0:
            handle_state_code('SKQuoteLib_GetStockByIndexLONG', state_code)
        return pStock.bstrStockNo

    @logger.catch
    def OnConnection(self, nKind, nCode):
        global win
        if (nKind == 3001):
            logger.info("Connection: Connected")
        elif (nKind == 3002):
            self.change_state(QuoteState.DISCONNECTED)
        elif (nKind == 3003):
            logger.info("Connection: Stocks ready!")
        elif (nKind == 3015):
            pass
        elif (nKind == 3021):
            logger.critical("Connection: Error!!!")
            self.change_state(QuoteState.ERROR)

    @logger.catch
    def OnNotifyHistoryTicks(self, sMarketNo, sStockIdx, nPtr, lDate, lTimehms, lTimemillismicros, nBid, nAsk, nClose, nQty, nSimulate):
        symbol = self.get_symbol(sMarketNo, sStockIdx)
        if nSimulate == 0:
            traded_time = datetime.strptime(str(lDate) + str(lTimehms).zfill(6), '%Y%m%d%H%M%S')
            price = nClose / 100

            self.CONN.push_historical_tick(symbol, {
                'time': traded_time,
                'price': price,
                'bid': nBid / 100,
                'ask': nAsk / 100,
                'vol': nQty
            })
            if self.trade_info_processor:
                self.trade_info_processor.on_tick(symbol, nBid, nAsk, nClose, nQty)
            self.kline_manager.on_historical_tick(symbol, traded_time, price, nQty)

    @logger.catch
    def OnNotifyTicks(self, sMarketNo, sStockIdx, nPtr, lDate, lTimehms, lTimemillismicros, nBid, nAsk, nClose, nQty, nSimulate):
        symbol = self.get_symbol(sMarketNo, sStockIdx)
        traded_time = datetime.strptime(str(lDate) + str(lTimehms).zfill(6), '%Y%m%d%H%M%S')
        price = nClose / 100
        bid = nBid / 100
        ask = nAsk / 100
        
        if nSimulate == 0:
            self.kline_manager.on_ticks(symbol, sMarketNo, traded_time, price, nQty, nSimulate)
            
            if self.trade_info_processor:
                self.trade_info_processor.on_tick(symbol, nBid, nAsk, nClose, nQty)
            
            self.CONN.push_tick(symbol, {
                'time': traded_time,
                'price': price,
                'bid': bid,
                'ask': ask,
                'vol': nQty
            })
            
            self.on_tick.emit(symbol, traded_time, price, bid, ask, nQty)

    @logger.catch
    def OnNotifyFutureTradeInfo(self, bstrStockNo, sMarketNo, nStockidx, nBuyTotalCount, nSellTotalCount, nBuyTotalQty, nSellTotalQty, nBuyDealTotalCount, nSellDealTotalCount):
        symbol = self.get_symbol(sMarketNo, nStockidx)
        if self.trade_info_processor:
            self.trade_info_processor.on_trade_info(symbol, nBuyTotalCount, nSellTotalCount, nBuyTotalQty, nSellTotalQty, nBuyDealTotalCount, nSellDealTotalCount)

    @logger.catch
    def OnNotifyServerTime(self,sHour,sMinute,sSecond,nTotal):
        """
        WARNING: If any event-handler executed more then five second, The given time will bugged
        """
        time_ = time(sHour, sMinute, sSecond)
        logger.info("Receive server time " + str(time_))

        self.kline_manager.on_time_update()

        if self.trade_info_processor:
            self.trade_info_processor.on_time(time_)

    def OnNotifyKLineData(self, bstrStockNo, bstrData):
        str_data = bstrData.split(", ")
        row = [str_data[0]] + [float(num) for num in str_data[1:]]
        self.kbar_buffer.append(row)

    def OnNotifyStockList(self,sMarketNo,bstrStockData):
        row = bstrStockData.split(';')
        if re.match('^##', row[0]):
            self.stock_list_lock.release()
        else:
            self.stock_list_buffer.append(row)

    def OnNotifyStrikePrices(self, bstrOptionData):
        opt_data = bstrOptionData.split(',')
        if re.match('^##', opt_data[0]):
            self.opt_list_lock.release()
        else:
            self.opt_list_buffer.append(opt_data)
