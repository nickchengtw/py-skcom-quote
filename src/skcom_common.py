
import os
from enum import Enum
from loguru import logger

import comtypes.client
comtypes.client.GetModule(os.path.split(os.path.realpath(__file__))[0] + r'\\..\\thirdparty\\SKCOM.dll')

import comtypes.gen.SKCOMLib as sk
skC = comtypes.client.CreateObject(sk.SKCenterLib,interface=sk.ISKCenterLib)
skOOQ = comtypes.client.CreateObject(sk.SKOOQuoteLib,interface=sk.ISKOOQuoteLib)
skO = comtypes.client.CreateObject(sk.SKOrderLib,interface=sk.ISKOrderLib)
skOSQ = comtypes.client.CreateObject(sk.SKOSQuoteLib,interface=sk.ISKOSQuoteLib)
skQ = comtypes.client.CreateObject(sk.SKQuoteLib,interface=sk.ISKQuoteLib)
skR = comtypes.client.CreateObject(sk.SKReplyLib,interface=sk.ISKReplyLib)


class QuoteState(Enum):
    DISCONNECTED = 1
    ERROR = 2
    CONNECTED = 3
    
    def __str__(self):
        return self.name


class MarketType(Enum):
    SECURITIES = 1
    FUTURES = 2
    OPTIONS = 3
    
    def __str__(self):
        return self.name


class SkcomError(Exception):
    pass


def handle_state_code(action, code):
    if code != 0:
        skmsg = skC.SKCenterLib_GetReturnCodeMessage(code)
        raise SkcomError(skmsg)
    logger.info(f"{action}: OK")


def api_login(user, password):
    handle_state_code(
        'SKCenterLib_Login',
        skC.SKCenterLib_Login(user, password)
    )
    logger.info("SKCOM login success")


class SKReply:
    def OnReplyMessage(self,bstrUserID, bstrMessages):
        sConfirmCode = -1
        logger.info(bstrMessages)
        return sConfirmCode
