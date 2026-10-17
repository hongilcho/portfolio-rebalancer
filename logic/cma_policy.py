"""Independent read/write switches and validated statement profile registry."""
import os

# Only code-reviewed, live-validated NH transaction profiles belong here.
# An observed candidate is tested locally. Production trust registration remains
# unapproved and blocked; environment/API input cannot grant that trust.
# Tests inject an explicitly synthetic profile only inside their process.
VALIDATED_STATEMENT_PROFILES=frozenset()


def writes_enabled():return os.getenv('CMA_INTEREST_WRITES_ENABLED','0')=='1'


def require_writes():
    if not writes_enabled():raise ValueError('CMA 장부 쓰기는 운영 승인 전까지 차단되어 있습니다.')


def automatic_ready():return bool(VALIDATED_STATEMENT_PROFILES)
