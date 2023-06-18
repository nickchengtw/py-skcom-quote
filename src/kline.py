
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, time


EMPTY_OHLCV = pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])


def pd_rule_to_minutes(rule):
    return {
        'T': 1,
        '5T': 5,
        '15T': 15,
        '30T': 30,
        '60T': 60
    }[rule]


"""
WARNING
This class is originally design for TW futures and options data from SKCOM-API.
Need test for new data-provider or new market.
"""
class KlineGenerator():
    def __init__(self, _, rule, first_tick_time, p_start, p_end, time_filter, last_trading_date=None):
        self._rule = rule
        self.timeframe_minutes = pd_rule_to_minutes(rule)
        self.first_tick_time = first_tick_time
        self.p_start = p_start
        self.p_end = p_end
        self.time_filter = time_filter
        self.last_trading_date = last_trading_date
        
        self._ticks = pd.DataFrame()
        self._closed = None

        self.last_time_updated = None
        self.dummy_count = 0

    def on_ticks(self, ticks, td=False):
        """
        WARNING: Can only handle ticks shorter then a trading-day
        """
        self.update_kline(ticks)
        kbars = self.resample_ohlcv()
        kbars = self.get_new_kbars(kbars)
        kbars = self.fill_empty_kbar(kbars)
        kbars = self.get_kbar_in_trading_period(kbars)
        kbars = self.get_kbar_in_trading_day(kbars)

        # TODO refactor this
        #
        # If you delete dummy first the tick may skip kbar that should
        # generate, cause some kbar disappear, so delete after kbar generated
        # if self.dummy_count:
        #     self._ticks = self._ticks[:-(self.dummy_count+1)].append(self._ticks[-1:])
        # self.dummy_count = 0

        return kbars

    def update_kline(self, ticks):
        if self._ticks.shape[0] == 0:
            dt = datetime(
                ticks.iloc[0].name.year, ticks.iloc[0].name.month, ticks.iloc[0].name.day,
                self.first_tick_time.hour, self.first_tick_time.minute
            )
            self._ticks = pd.DataFrame(
                        [[ticks.iloc[0].Price, 0]],
                        index=[dt],
                        columns=['Price', 'Volume']
                    )
        self._ticks = self._ticks.append(ticks)

    def resample_ohlcv(self):
        ohlc = self._ticks.Price.resample(self._rule, label='right').ohlc()
        ohlc.columns = ['Open', 'High', 'Low', 'Close']
        vol = self._ticks.Volume.resample(self._rule, label='right').sum()
        ohlcv = ohlc.join(vol)
        return ohlcv

    def get_new_kbars(self, kbars):
        new_kbars = EMPTY_OHLCV
        if kbars.shape[0] > 1:
            closed = kbars.iloc[-2]
            self._ticks = self._ticks.loc[self._ticks.index >= closed.name]
            assert self._ticks.shape[0] > 0
            self._closed = closed.name
            new_kbars = kbars[:closed.name]
        return new_kbars

    @staticmethod
    def fill_empty_kbar(ohlcv):
        if len(ohlcv) == 0:
            return EMPTY_OHLCV
        ohlcv_arr = ohlcv.to_numpy()
        for i in range(1, len(ohlcv_arr)):
            if np.isnan(ohlcv_arr[i][0]):
                ohlcv_arr[i] = np.array([ohlcv_arr[i-1][3]]*4 + [0])
        kbars = pd.DataFrame(ohlcv_arr, columns=['Open', 'High', 'Low', 'Close', 'Volume'], index=ohlcv.index)
        return kbars

    def get_kbar_in_trading_period(self, kbars):
        if len(kbars) == 0:
            return EMPTY_OHLCV
        return kbars[[self.time_filter(t) for t in kbars.index]]

    def get_kbar_in_trading_day(self, kbars):
        """
        This method works because SKCOM-API
        only return ticks in current day-period and
        previous night-period
        """
        index_before_end = []
        index_after_start = []
        for i in kbars.index:
            if i.time() == self.p_start:
                for j in reversed(kbars.index):
                    if j < i:
                        break
                    if j.time() == self.p_end:
                        break
                    index_after_start.append(j)
                index_after_start.reverse()
                break
            index_before_end.append(i)
        kbars = kbars.loc[index_before_end + index_after_start]
        return kbars

    def update_time_updated(self, ts):
        # self.last_time_updated = ts
        pass

    def get_timeout_kbars(self, ts):
        df = EMPTY_OHLCV
        # if (len(self._ticks) > 0
        #         and self.last_time_updated
        #         and ts - self.last_time_updated > timedelta(seconds=4)):
        #     df = self.on_ticks(pd.DataFrame(
        #         [[self._ticks.iloc[-1].Price, 0]],
        #         index=[ts],
        #         columns=['Price', 'Volume']
        #     ))
        #     self.dummy_count += 1
        # self.last_time_updated = ts
        return df


class LiveKlineGenerator():
    def __init__(self, _, rule, first_tick_time, p_start, p_end, time_filter):
        self._rule = rule
        self._ticks = pd.DataFrame()
        self._closed = None

        self.first_tick_time = first_tick_time
        self.p_start = p_start
        self.p_end = p_end
        self.time_filter = time_filter

    def on_ticks(self, ticks, td=False):
        """
        WARNING
        Only first and last period will be return
        """
        self._ticks = self._ticks.append(ticks)
        ohlc = self._ticks.Price.resample(self._rule, label='right').ohlc()
        ohlc.columns = ['Open', 'High', 'Low', 'Close']
        vol = self._ticks.Volume.resample(self._rule, label='right').sum()
        ohlcv = ohlc.join(vol)

        # Fill empty bars
        ohlcv_arr = ohlcv.to_numpy()
        for i in range(1, len(ohlcv_arr)):
            if np.isnan(ohlcv_arr[i][0]):
                ohlcv_arr[i] = np.array([ohlcv_arr[i-1][3]]*4 + [0])

        kbars = pd.DataFrame(ohlcv_arr, columns=['Open', 'High', 'Low', 'Close', 'Volume'], index=ohlc.index)

        # Clear reset time
        kbars = kbars[[self.time_filter(t) for t in kbars.index]]

        # Clear holiday
        index_before_end = []
        index_after_start = []
        for i in kbars.index:
            index_before_end.append(i)
            if i.time() == self.p_end:
                for j in reversed(kbars.index):
                    if j <= i:
                        break
                    index_after_start.append(j)
                    if j.time() == self.p_start:
                        break
                index_after_start.reverse()
                break

        kbars = kbars.loc[index_before_end + index_after_start]

        # Remove and return complete bars
        if kbars.shape[0] > 1:
            closed = kbars.iloc[-2]
            self._ticks = self._ticks.loc[self._ticks.index >= closed.name]
            assert self._ticks.shape[0] > 0
            self._closed = closed.name
            return kbars[:closed.name]
        return EMPTY_OHLCV
