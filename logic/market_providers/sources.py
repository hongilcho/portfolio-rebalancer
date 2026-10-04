"""Explicit source dependencies for a quote request; no clients created here."""
from dataclasses import dataclass

from .namuh import NamuhQuotes
from .naver import NaverQuotes
from .yahoo import YahooQuotes


@dataclass(frozen=True)
class QuoteSources:
    naver: NaverQuotes
    namuh: NamuhQuotes
    yahoo: YahooQuotes
