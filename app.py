"""台股本益比河流圖估價小工具

用法：在這個資料夾開終端機執行
    streamlit run app.py
會自動開瀏覽器，輸入股票代號按查詢即可。
"""
from __future__ import annotations

import streamlit as st

from calculator import compute_valuation
from scraper import ScrapeError, fetch_price_and_year_per, fetch_quarterly_eps

st.set_page_config(page_title="台股本益比河流圖估價", page_icon="📈")

st.title("📈 台股本益比河流圖估價")
st.caption("資料來源：MoneyDJ理財網。僅供參考，不是投資建議。")

stock_id = st.text_input("股票代號", value="4979", max_chars=10).strip()
query = st.button("查詢", type="primary")

if query and stock_id:
    try:
        with st.spinner(f"正在抓 {stock_id} 的資料…"):
            price_data = fetch_price_and_year_per(stock_id)
            eps_quarters = fetch_quarterly_eps(stock_id, quarters=4)

            window = price_data["year_per"]
            result = compute_valuation(
                current_price=price_data["current_price"],
                current_per=price_data["current_per"],
                year_per=window,
                eps_quarters=eps_quarters,
            )
    except ScrapeError as e:
        st.error(f"抓資料失敗：{e}")
    except Exception as e:  # noqa: BLE001 - 顯示給非工程師使用者看的錯誤訊息
        st.error(f"發生錯誤：{e}")
    else:
        st.subheader(f"{stock_id}　現價 {result.current_price:.2f} 元　（目前本益比 {result.current_per:.2f}）")

        col1, col2, col3 = st.columns(3)
        col1.metric(
            "便宜價",
            f"{result.cheap_price:.1f} 元" if result.cheap_price is not None else "無法計算",
        )
        col2.metric("合理價", f"{result.fair_price:.1f} 元")
        col3.metric(
            "貴價",
            f"{result.expensive_price:.1f} 元" if result.expensive_price is not None else "無法計算",
        )

        # 現價相對位置
        if result.cheap_price is not None and result.current_price < result.cheap_price:
            st.success("現價低於便宜價，落在便宜區間。")
        elif result.expensive_price is not None and result.current_price > result.expensive_price:
            st.warning("現價高於貴價，落在昂貴區間。")
        else:
            st.info("現價落在便宜價與貴價之間。")

        with st.expander("計算細節"):
            eps_detail = ", ".join(
                f"{q['period']}={q['eps']:.2f}" for q in result.eps_quarters
            )
            st.write(f"近 4 季 EPS 加總：**{result.eps_sum:.2f}** 元（{eps_detail}）")
            st.write(
                f"便宜本益比：**{result.cheap_per:.2f}**"
                if result.cheap_per is not None
                else "便宜本益比：無有效資料"
            )
            st.write(f"　└ 採計年度：{', '.join(str(y) for y in sorted(result.cheap_years_used, reverse=True)) or '無'}")
            st.write(
                f"貴本益比：**{result.expensive_per:.2f}**"
                if result.expensive_per is not None
                else "貴本益比：無有效資料"
            )
            st.write(f"　└ 採計年度：{', '.join(str(y) for y in sorted(result.expensive_years_used, reverse=True)) or '無'}")
            st.write(f"合理本益比（＝目前本益比）：**{result.fair_per:.2f}**")

            if result.excluded_notes:
                st.write("排除的年度：")
                for note in result.excluded_notes:
                    st.write(f"　⚠️ {note}")

        with st.expander("原始年度本益比資料（近 5 年，含今年至今）"):
            rows = []
            for y in sorted(window.keys(), reverse=True)[:5]:
                v = window[y]
                rows.append(
                    {
                        "年度": y,
                        "最高本益比": v["high"] if v["high"] is not None else "無資料",
                        "最低本益比": v["low"] if v["low"] is not None else "無資料",
                    }
                )
            st.table(rows)
elif query:
    st.warning("請先輸入股票代號")
