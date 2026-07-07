"""從 MoneyDJ 抓取個股的本益比河流圖與季 EPS 原始資料。"""
from __future__ import annotations

from io import StringIO

import pandas as pd
import requests
import urllib3

# MoneyDJ 的憑證鏈缺少 Subject Key Identifier 欄位，部分環境（如 Streamlit Cloud）
# 用較嚴格的 OpenSSL 版本會直接判定憑證無效而連線失敗，本機環境則不受影響。
# 這裡只讀取公開股價/EPS 資料、不傳送任何帳密，因此關閉憑證驗證作為因應。
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


class ScrapeError(RuntimeError):
    """網站資料抓不到或格式跟預期不符時丟出。"""


def _get_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=10, verify=False)
    resp.raise_for_status()
    resp.encoding = "big5"
    return resp.text


def _rows_as_str(df: pd.DataFrame):
    """逐列回傳字串化後的儲存格，不依賴 df.astype(str)（table 裡混雜型別時不可靠）。"""
    for row in df.values.tolist():
        yield [str(c).strip() for c in row]


def _find_row(df: pd.DataFrame, label: str) -> list[str] | None:
    """在表格中找第一欄等於 label 的那一列，回傳該列其餘欄位（字串）。"""
    for row in _rows_as_str(df):
        if row and row[0] == label:
            return row[1:]
    return None


def _find_label_value(df: pd.DataFrame, label: str) -> str | None:
    """在表格中找到內容剛好等於 label 的儲存格，回傳同一列中緊接在後面的值。"""
    for row in _rows_as_str(df):
        for i, cell in enumerate(row):
            if cell == label and i + 1 < len(row):
                return row[i + 1]
    return None


def fetch_price_and_year_per(stock_id: str) -> dict:
    """回傳目前股價、目前本益比，以及各年度(西元年)最高/最低本益比。

    網站來源：https://concords.moneydj.com/z/zc/zca/zca_{stock_id}.djhtm
    """
    url = f"https://concords.moneydj.com/z/zc/zca/zca_{stock_id}.djhtm"
    html = _get_html(url)
    tables = pd.read_html(StringIO(html))

    current_price = None
    current_per = None
    year_table_df = None

    for df in tables:
        if current_price is None:
            v = _find_label_value(df, "收盤價")
            if v is not None:
                current_price = float(v)
        if current_per is None:
            v = _find_label_value(df, "本益比")
            if v is not None:
                current_per = float(v)
        if _find_row(df, "最高本益比") is not None:
            year_table_df = df

    if current_price is None or current_per is None:
        raise ScrapeError(f"抓不到 {stock_id} 的目前股價或目前本益比，網站結構可能變了")
    if year_table_df is None:
        raise ScrapeError(f"抓不到 {stock_id} 的年度本益比表格，網站結構可能變了")

    years_roc = _find_row(year_table_df, "年度")
    highs = _find_row(year_table_df, "最高本益比")
    lows = _find_row(year_table_df, "最低本益比")
    if not years_roc or not highs or not lows:
        raise ScrapeError(f"{stock_id} 的年度本益比表格欄位對不上，網站結構可能變了")

    def clean(v: str) -> float | None:
        v = v.strip()
        if v in ("N/A", "nan", "", "-"):
            return None
        try:
            f = float(v)
        except ValueError:
            return None
        # 網站用 0.00 代表「當年度曾虧損、無法計算本益比」
        return None if f == 0.0 else f

    year_per: dict[int, dict[str, float | None]] = {}
    for y, h, l in zip(years_roc, highs, lows):
        try:
            year_west = int(float(y)) + 1911
        except ValueError:
            continue
        year_per[year_west] = {"high": clean(h), "low": clean(l)}

    return {
        "current_price": current_price,
        "current_per": current_per,
        "year_per": year_per,
    }


def fetch_quarterly_eps(stock_id: str, quarters: int = 4) -> list[dict]:
    """回傳最近幾季的 EPS，最新的一季在最前面。

    網站來源：https://concords.moneydj.com/z/zc/zcq/zcq_{stock_id}.djhtm

    注意：這個頁面的季報表不是正常的 HTML 表格結構，整張表被塞進單一個
    文字區塊、欄位間用空白分隔（例如 "每股盈餘 1.62 1.69 ... 加權平均股數"），
    所以用切字串的方式解析，而不是逐列讀表格。
    """
    url = f"https://concords.moneydj.com/z/zc/zcq/zcq_{stock_id}.djhtm"
    html = _get_html(url)
    tables = pd.read_html(StringIO(html))

    blob = None
    for df in tables:
        for row in df.values.tolist():
            for cell in row:
                cell_str = str(cell)
                if "期別" in cell_str and "每股盈餘" in cell_str:
                    blob = cell_str
                    break
            if blob:
                break
        if blob:
            break

    if blob is None:
        raise ScrapeError(f"抓不到 {stock_id} 的季報表資料，網站結構可能變了")

    tokens = blob.split()

    def tokens_between(label: str, stop_label: str) -> list[str]:
        try:
            start = tokens.index(label) + 1
        except ValueError as exc:
            raise ScrapeError(f"{stock_id} 季報表裡找不到「{label}」欄位") from exc
        end = start
        while end < len(tokens) and tokens[end] != stop_label:
            end += 1
        return tokens[start:end]

    periods = tokens_between("期別", "種類")
    if not periods:
        raise ScrapeError(f"{stock_id} 季報表解析不到期別欄位，網站結構可能變了")

    try:
        eps_start = tokens.index("每股盈餘") + 1
    except ValueError as exc:
        raise ScrapeError(f"{stock_id} 季報表裡找不到「每股盈餘」欄位") from exc
    eps_values = tokens[eps_start : eps_start + len(periods)]

    if len(eps_values) < quarters:
        raise ScrapeError(
            f"{stock_id} 抓到的季 EPS 只有 {len(eps_values)} 筆，不足 {quarters} 季"
        )

    result = []
    for period, eps in zip(periods, eps_values):
        try:
            result.append({"period": period, "eps": float(eps)})
        except ValueError as exc:
            raise ScrapeError(f"{stock_id} 的 EPS 數值「{eps}」無法轉成數字") from exc

    return result[:quarters]
