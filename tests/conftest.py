# pytest 설정 — 비동기 테스트를 asyncio 백엔드로 고정한다
import pytest


@pytest.fixture
def anyio_backend():
    """anyio 테스트를 asyncio로만 돌린다 (trio 의존성 불필요)."""
    return "asyncio"
