
import abc
import json
from datetime import time
from loguru import logger


class TradeInfoProcessor(abc.ABC):
    @abc.abstractmethod
    def on_tick(self, symbol, nBid, nAsk, nClose, nQty):
        return NotImplemented

    @abc.abstractmethod
    def on_trade_info(self, symbol, nBuyTotalCount, nSellTotalCount, nBuyTotalQty, nSellTotalQty, nBuyDealTotalCount, nSellDealTotalCount):
        return NotImplemented

    @abc.abstractmethod
    def on_time(self, t):
        return NotImplemented
