"""Lazy, shared HTTP connection reuse for public quote endpoints."""
import threading

import requests
from requests.adapters import HTTPAdapter


class QuoteHTTPClient:
    def __init__(self, session_factory=requests.Session):
        self._session_factory = session_factory
        self._session = None
        self._lock = threading.Lock()

    def session(self):
        if self._session is None:
            with self._lock:
                if self._session is None:
                    session = self._session_factory()
                    session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                                      'Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'application/json, text/plain, */*',
                    })
                    adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
                    session.mount('https://', adapter)
                    session.mount('http://', adapter)
                    self._session = session
        return self._session

    def get(self, url, headers=None, timeout=2.0):
        return self.session().get(url, headers=headers, timeout=timeout)


quote_http_client = QuoteHTTPClient()
