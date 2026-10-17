"""Independent read/write switches and validated statement profile registry."""
import os

# Only code-reviewed, live-validated NH transaction profiles belong here.
# NH_COMMON_CMA_PAID_V1 was observed through the existing app on 2026-10-15,
# including actual interest/tax, bank cash/principal chains and the evening sweep.
# The user explicitly approved persistent registration and automatic CMA income
# on 2026-10-17. This does not enable writes or any account's automatic policy.
# Environment/API input cannot add trusted profiles; synthetic tests stay local.
VALIDATED_STATEMENT_PROFILES=frozenset({'NH_COMMON_CMA_PAID_V1'})


def writes_enabled():return os.getenv('CMA_INTEREST_WRITES_ENABLED','0')=='1'


def require_writes():
    if not writes_enabled():raise ValueError('CMA 장부 쓰기는 운영 승인 전까지 차단되어 있습니다.')


def automatic_ready():return bool(VALIDATED_STATEMENT_PROFILES)
