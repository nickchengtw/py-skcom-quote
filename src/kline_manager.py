
import re
import pandas as pd
from datetime import datetime, time, timedelta
from loguru import logger

from src.skcom_common import MarketType
from src.kline import KlineGenerator

class KlineManager:
    def __init__(self, conn) -> None:
        self.conn = conn
        
        self.market_types = {}
        self.hist_kline_loaded = set()
        self.historical_buffer = {}
        self.is_historical_end = {}
        self.kline_generators = {}

    @staticmethod
    def is_sec_trading(t):
        return time(9) < t.time() and t.time() <= time(13, 30)

    @staticmethod
    def is_day_market(now):
        return time(8, 45) <= now.time() and now.time() <= time(13, 45)

    @staticmethod
    def is_night_market(now):
        return time(15) <= now.time() or now.time() <= time(5)

    @staticmethod
    def kbar_time_valid(t):
        return (
            (time(8, 45) < t.time() and t.time() <= time(13, 45))
            or time(15) < t.time()
            or t.time() <= time(5)
        )

    @staticmethod
    def aligned_kbar_time_valid(t):
        return (
            (time(8) < t.time() and t.time() <= time(13))
            or time(15) < t.time()
            or t.time() <= time(5)
        )

    @staticmethod
    def tf_align_to_hour_start(df):
        new_df = df.copy()
        new_df.index = [
            t - timedelta(minutes=45) if KlineManager.is_day_market(t) else t
            for t in new_df.index]
        return new_df

    @staticmethod
    def tf_recover_original(df):
        new_df = df.copy()
        new_df.index = [
            t + timedelta(minutes=45) if (time(8) <= t.time() and t.time() <= time(13)) else t
            for t in new_df.index]
        return new_df

    def init_symbol(self, market_type, symbol):
        logger.info(f'Init symbol {symbol}')
        self.market_types[symbol] = market_type
        self.historical_buffer[symbol] = []
        self.is_historical_end[symbol] = False
        self.kline_generators[symbol] = {}
        generator = self.kline_generators[symbol]
        if market_type == MarketType.SECURITIES:
            generator['M1'] = KlineGenerator(symbol, 'T', time(9), time(9, 1), time(13, 30), self.is_sec_trading)
            generator['M5'] = KlineGenerator(symbol, '5T', time(9), time(9, 5), time(13, 30), self.is_sec_trading)
            generator['M15'] = KlineGenerator(symbol, '15T', time(9), time(9, 15), time(13, 30), self.is_sec_trading)
            generator['M30'] = KlineGenerator(symbol, '30T', time(9), time(9, 30), time(13, 30), self.is_sec_trading)
            generator['H1'] = KlineGenerator(symbol, '60T', time(9), time(10), time(14), lambda t: time(9) < t.time() and t.time() <= time(14))
        elif market_type in [MarketType.FUTURES, MarketType.OPTIONS]:
            generator['M1'] = KlineGenerator(symbol, 'T', time(15), time(8, 46), time(5), self.kbar_time_valid)
            generator['M5'] = KlineGenerator(symbol, '5T', time(15), time(8, 50), time(5), self.kbar_time_valid)
            generator['M15'] = KlineGenerator(symbol, '15T', time(15), time(9), time(5), self.kbar_time_valid)
            generator['M30'] = KlineGenerator(symbol, '30T', time(15), time(8, 30), time(5), self.aligned_kbar_time_valid)
            generator['H1'] = KlineGenerator('', '60T', time(15), time(9), time(5), self.aligned_kbar_time_valid)

    def on_historical_tick(self, symbol, time_, price, qty):
        self.historical_buffer[symbol].append([time_, price, qty])

    def generate_historical_kline(self, sMarketNo, symbol):
        logger.info(f"{symbol} Historical buffer size={len(self.historical_buffer[symbol])}")
        if len(self.historical_buffer[symbol]) > 0:
            df = pd.DataFrame(
                    [row[1:] for row in self.historical_buffer[symbol]],
                    index=[pd.Timestamp(row[0]) for row in self.historical_buffer[symbol]],
                    columns=['Price', 'Volume']
                )

            generator = self.kline_generators[symbol]
            if sMarketNo > 1:
                kbars_h1 = self.tf_recover_original(generator['H1'].on_ticks(self.tf_align_to_hour_start(df)))
                kbars_m30 = self.tf_recover_original(generator['M30'].on_ticks(self.tf_align_to_hour_start(df)))
            else:
                kbars_h1 = generator['H1'].on_ticks(df, td=True)
                kbars_m30 = generator['M30'].on_ticks(df)
            kbars_m15 = generator['M15'].on_ticks(df)
            kbars_m5 = generator['M5'].on_ticks(df)
            kbars_m1 = generator['M1'].on_ticks(df)

            self.conn.kline_write_historical(symbol, 'H1', kbars_h1)
            self.conn.kline_write_historical(symbol, 'M30', kbars_m30)
            self.conn.kline_write_historical(symbol, 'M15', kbars_m15)
            self.conn.kline_write_historical(symbol, 'M5', kbars_m5)
            self.conn.kline_write_historical(symbol, 'M1', kbars_m1)
            self.is_historical_end[symbol] = True

    def on_ticks(self, symbol, sMarketNo, time_, price, nQty, nSimulate):
        if not self.is_historical_end[symbol]:
            self.generate_historical_kline(sMarketNo, symbol)
        if nSimulate == 0:
            self.update_kline(sMarketNo, nQty, symbol, time_, price)

    def update_kline(self, sMarketNo, nQty, symbol, traded_time, price):
        df = pd.DataFrame(
                [[price, nQty]],
                index=[traded_time],
                columns=['Price', 'Volume']
            )

        generator = self.kline_generators[symbol]
        if sMarketNo > 1:
            kbars_h1 = self.tf_recover_original(generator['H1'].on_ticks(self.tf_align_to_hour_start(df)))
            kbars_m30 = self.tf_recover_original(generator['M30'].on_ticks(self.tf_align_to_hour_start(df)))
        else:
            kbars_h1 = generator['H1'].on_ticks(df, td=True)
            kbars_m30 = generator['M30'].on_ticks(df)
        kbars_m15 = generator['M15'].on_ticks(df)
        kbars_m5 = generator['M5'].on_ticks(df)
        kbars_m1 = generator['M1'].on_ticks(df)

        for g in generator.values():
            g.update_time_updated(datetime.now())

        for ts, _ in kbars_m1.iterrows():
            if ts in kbars_h1.index:
                self.conn.kline_add_new(symbol, 'H1', kbars_h1.loc[ts])
            if ts in kbars_m30.index:
                self.conn.kline_add_new(symbol, 'M30', kbars_m30.loc[ts])
            if ts in kbars_m15.index:
                self.conn.kline_add_new(symbol, 'M15', kbars_m15.loc[ts])
            if ts in kbars_m5.index:
                self.conn.kline_add_new(symbol, 'M5', kbars_m5.loc[ts])
            self.conn.kline_add_new(symbol, 'M1', kbars_m1.loc[ts])

    def on_time_update(self):
        for symbol, gens in self.kline_generators.items():
            # TODO Now only for option, support other in future
            if self.is_historical_end[symbol] and self.market_types[symbol] == MarketType.OPTIONS:
                now = datetime.now()
                generator = self.kline_generators[symbol]
                kbars_m15 = generator['M15'].get_timeout_kbars(now)
                kbars_m5 = generator['M5'].get_timeout_kbars(now)
                kbars_m1 = generator['M1'].get_timeout_kbars(now)
                for ts, _ in kbars_m1.iterrows():
                    # TODO Will add in future
                    #
                    # if ts in kbars_h1.index:
                    #     self.conn.kline_add_new(symbol, 'H1', kbars_h1.loc[ts])
                    # if ts in kbars_m30.index:
                    #     self.conn.kline_add_new(symbol, 'M30', kbars_m30.loc[ts])
                    if ts in kbars_m15.index:
                        self.conn.kline_add_new(symbol, 'M15', kbars_m15.loc[ts])
                    if ts in kbars_m5.index:
                        self.conn.kline_add_new(symbol, 'M5', kbars_m5.loc[ts])
                    self.conn.kline_add_new(symbol, 'M1', kbars_m1.loc[ts])
