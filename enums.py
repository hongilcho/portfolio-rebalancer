from enum import Enum

class Currency(str, Enum):
    KRW = "KRW"
    USD = "USD"

class AccountType(str, Enum):
    GENERAL = "종합매매"
    PENSION = "연금저축계좌"
    IRP = "IRP"
    ISA = "ISA"
    CMA = "CMA"
    GOLD = "금현물"
    
class TradeType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"
