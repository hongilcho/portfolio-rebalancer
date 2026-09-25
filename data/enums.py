"""
포트폴리오 리밸런서 공통 열거형(Enum) 정의 모듈
=================================================
화폐 단위, 계좌 유형, 거래 유형 등 시스템 전반에서 사용되는 표준 상수 열거형을 정의합니다.
"""

from enum import Enum

class Currency(str, Enum):
    """기준 통화 코드 열거형"""
    KRW = "KRW"  # 대한민국 원화
    USD = "USD"  # 미국 달러

class AccountType(str, Enum):
    """
    계좌 유형 열거형
    각 계좌는 세제 혜택 및 운용 제약(위험자산 70% 제한 등)이 상이합니다.
    """
    GENERAL = "종합매매"     # 일반 과세 위탁 계좌 (자유 입출금 및 전 종목 거래 가능)
    PENSION = "연금저축계좌"  # 연금저축펀드 계좌 (세액공제 및 과세이연 혜택)
    IRP = "IRP"             # 개인형 퇴직연금 (세액공제 혜택, 위험자산 70% 한도 규제 적용)
    ISA = "ISA"             # 개인종합자산관리계좌 (비과세/분리과세 혜택)
    CMA = "CMA"             # 종합자산관리계좌 (수시입출금 단기 자금 보관용)
    GOLD = "금현물"         # KRX 금시장 전용 비과세 계좌
    
class TradeType(str, Enum):
    """거래 및 자금 이동 유형 열거형"""
    BUY = "BUY"            # 종목 매수
    SELL = "SELL"          # 종목 매도
    DEPOSIT = "DEPOSIT"    # 현금 입금
    WITHDRAW = "WITHDRAW"  # 현금 출금
