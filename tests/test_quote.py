
import sys
import os
import unittest
from unittest import mock
import pandas as pd
from datetime import datetime, time


from skcom_common import MarketType, SkcomError
from kline import KlineGenerator
from trade_info import TradeInfoProcessor
from main import TWQuote
from kline_manager import KlineManager


class TestQuote(unittest.TestCase):
    @mock.patch('main.TWQuote.disconnect')
    @mock.patch('main.TWQuote.connect')
    def test_quote_until_success(self, mock_connect, _):
        mock_connect.side_effect = [SkcomError("Unable to connect"), None]
        q = TWQuote('t1', None, None, None)
        q.connect_until_success()
        self.assertTrue(mock_connect.call_count == 2)
    
    @mock.patch('main.TWQuote.load_kline')
    @mock.patch('main.TWQuote.request_ticks')
    def test_subscribe_market(self, _, mock_load_kline):
        mock_ui = mock.Mock()
        q = TWQuote('t1', None, None, mock_ui)
        q.subscribe_market(MarketType.FUTURES, 'TX00')
        q.subscribe_market(MarketType.FUTURES, 'TX00')
        self.assertTrue(mock_load_kline.call_count == 1)
    
    @mock.patch('main.TWQuote.get_raw_kline')
    def test_get_kline(self, mock_kline):
        mock_kline.side_effect = [
            [['-195/44/12 233:140', -0.0, 0.0, 0.0, -7.88965172376729e+22, -1162025816.0]],
            [['2022/04/18 08:46', 10, 11, 9, 10, 1]]
        ]
        q = TWQuote('t1', None, None, None)
        kbars = q.kline('TX00', 1)
        kbars.index[0]


class TestCalculation(unittest.TestCase):
    def setUp(self) -> None:
        self.test_tick = pd.read_csv('tests/data/test_tick.csv', parse_dates=True, index_col=0)

    def test_generator_small_timeframe(self):
        gen = KlineGenerator('', 'T', time(15), time(8, 46), time(5), KlineManager.kbar_time_valid)
        kbars = gen.on_ticks(self.test_tick)
        self.assertTrue(kbars.iloc[0].name == datetime(2021, 7, 5, 15, 1))
        self.assertTrue(
            all(kbars.loc[datetime(2021, 7, 8, 9, 46)].to_numpy() == [0.9, 1., 0.8, 1., 9. ])
            )
        self.assertNotIn(datetime(2021, 7, 6, 8, 46), kbars.index)
        self.assertNotIn(datetime(2021, 7, 8, 13, 46), kbars.index)
        self.assertIn(datetime(2021, 7, 8, 8, 46), kbars.index)
        self.assertIn(datetime(2021, 7, 8, 15, 5), kbars.index)

    def test_generator_big_timeframe(self):
        gen = KlineGenerator('', '60T', time(15), time(9), time(5), KlineManager.kbar_time_valid)
        kbars = KlineManager.tf_recover_original(gen.on_ticks(KlineManager.tf_align_to_hour_start(self.test_tick)))
        self.assertTrue(kbars.iloc[0].name == datetime(2021, 7, 5, 16))
        self.assertTrue(
            all(kbars.loc[datetime(2021, 7, 8, 10, 45)].to_numpy() == [0.9, 1., 0.8, 0.9, 11.])
        )

    def test_return_when_no_new(self):
        g = KlineGenerator('', 'T', time(15), time(8, 46), time(5), KlineManager.kbar_time_valid)
        kbars = g.on_ticks(pd.DataFrame(
            [[9, 1],
             [10, 1]],
            index=[
                datetime(2021, 2, 26, 15),
                datetime(2021, 2, 26, 15, 0, 30)
            ],
            columns=['Price', 'Volume']
        ))
        _ = kbars['Open']
