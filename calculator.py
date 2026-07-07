"""本益比河流圖估價計算邏輯。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValuationResult:
    current_price: float
    current_per: float
    eps_sum: float
    eps_quarters: list[dict]

    cheap_per: float | None
    cheap_price: float | None
    cheap_years_used: list[int]

    expensive_per: float | None
    expensive_price: float | None
    expensive_years_used: list[int]

    fair_per: float
    fair_price: float

    excluded_notes: list[str] = field(default_factory=list)


def compute_valuation(
    current_price: float,
    current_per: float,
    year_per: dict[int, dict[str, float | None]],
    eps_quarters: list[dict],
    window_years: int = 5,
) -> ValuationResult:
    """
    year_per: {西元年: {"high": 最高本益比或None, "low": 最低本益比或None}}
              年度由大到小取最近 window_years 年，包含當年度（今年至今，即使尚未結束）。
    eps_quarters: [{"period": "2026.1Q", "eps": 1.62}, ...]，取全部加總為近 N 季 EPS。

    規則（Andy 確認版本）：
    - 便宜價／貴價：固定看最近 window_years 個年度（含今年），每年分別檢查最高／最低本益比
      是否有效；缺值的那一年就不計入該項平均，分母用「實際有效年度數」，不用 0 湊。
    - 合理價：直接用「目前本益比」乘以近 4 季 EPS 加總（等同用目前股價當基準點）。
    """
    sorted_years = sorted(year_per.keys(), reverse=True)
    window = sorted_years[:window_years]

    excluded_notes: list[str] = []

    high_pairs = [(y, year_per[y]["high"]) for y in window]
    valid_highs = [(y, v) for y, v in high_pairs if v is not None]
    for y, v in high_pairs:
        if v is None:
            excluded_notes.append(f"{y} 年最高本益比無效（當年度曾虧損，不計入貴價平均）")

    low_pairs = [(y, year_per[y]["low"]) for y in window]
    valid_lows = [(y, v) for y, v in low_pairs if v is not None]
    for y, v in low_pairs:
        if v is None:
            excluded_notes.append(f"{y} 年最低本益比無效（當年度曾虧損，不計入便宜價平均）")

    expensive_per = (
        sum(v for _, v in valid_highs) / len(valid_highs) if valid_highs else None
    )
    cheap_per = sum(v for _, v in valid_lows) / len(valid_lows) if valid_lows else None

    eps_sum = sum(q["eps"] for q in eps_quarters)

    expensive_price = expensive_per * eps_sum if expensive_per is not None else None
    cheap_price = cheap_per * eps_sum if cheap_per is not None else None

    fair_per = current_per
    fair_price = fair_per * eps_sum

    return ValuationResult(
        current_price=current_price,
        current_per=current_per,
        eps_sum=eps_sum,
        eps_quarters=eps_quarters,
        cheap_per=cheap_per,
        cheap_price=cheap_price,
        cheap_years_used=[y for y, _ in valid_lows],
        expensive_per=expensive_per,
        expensive_price=expensive_price,
        expensive_years_used=[y for y, _ in valid_highs],
        fair_per=fair_per,
        fair_price=fair_price,
        excluded_notes=excluded_notes,
    )
