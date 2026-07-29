"""google_finance 데이터 모델.

파이프라인에서 모듈 간 데이터를 전달하는 데 사용하는
dataclass를 정의한다.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class StockPrice:
    """Google Finance에서 수집한 종목 시세 1건."""

    symbol: str
    name: str
    current_price: float
    previous_close: float
    open_price: float
    change_percent: float
    collected_at: datetime = field(default_factory=datetime.now)


@dataclass
class StockReport:
    """최종 결과물. 종목 시세 + LLM 등락 분석을 합친 보고서 1건."""

    symbol: str
    name: str
    current_price: float
    previous_close: float
    open_price: float
    change_percent: float
    reason: str
    collected_at: datetime = field(default_factory=datetime.now)
