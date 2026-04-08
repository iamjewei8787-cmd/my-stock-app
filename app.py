import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import datetime

# 1. 介面設定
st.set_page_config(page_title="台股波段選股神器", page_icon="📈", layout="centered")
st.title("📈 台股波段選股神器 (手機版)")
st.markdown("**策略：** 排除 ETF | 尋找 MACD 翻紅 + KD 黃金交叉 | 依成交量排序挑選前 10 檔")

# 2. 定義股票池 (為了確保雲端執行速度，這裡放入 50 檔熱門中大型股作為示範)
# 實戰中，你可以將台股上市櫃 1700 檔名單存成 CSV 檔在這裡讀取
DEFAULT_STOCKS = [
    "2330.TW", "2317.TW", "2454.TW", "2382.TW", "3231.TW", "2308.TW", "1519.TW", "1514.TW", 
    "2356.TW", "5371.TWO", "2603.TW", "2609.TW", "2615.TW", "3481.TW", "2409.TW", "2303.TW",
    "2881.TW", "2882.TW", "2891.TW", "2324.TW", "2376.TW", "3037.TW", "8046.TW", "3189.TW",
    "6274.TWO", "3017.TW", "2368.TW", "2313.TW", "2353.TW", "2449.TW", "2301.TW", "3034.TW"
]

# 3. 核心選股邏輯
def run_screener(stock_list):
    buy_list = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_stocks = len(stock_list)
    
    for i, ticker in enumerate(stock_list):
        # 更新進度條
        progress_bar.progress((i + 1) / total_stocks)
        status_text.text(f"正在掃描: {ticker} ({i+1}/{total_stocks})...")
        
        # 排除 ETF (簡單判斷：非 00 開頭)
        pure_ticker = ticker.split('.')[0]
        if pure_ticker.startswith('00'):
            continue
            
        try:
            # 抓取近半年資料
            df = yf.download(ticker, period="6mo", progress=False)
            if df.empty or len(df) < 50:
                continue
                
            # 計算指標
            macd = df.ta.macd(fast=12, slow=26, signal=9)
            df = pd.concat([df, macd], axis=1)
            stoch = df.ta.stoch(high='High', low='Low', close='Close', k=9, d=3, smooth_k=3)
            df = pd.concat([df, stoch], axis=1)
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            macd_hist_col = [c for c in df.columns if 'MACDh' in c][0]
            k_col = [c for c in df.columns if 'STOCHk' in c][0]
            d_col = [c for c in df.columns if 'STOCHd' in c][0]
            
            # 條件：量大 (> 3000張) + MACD翻紅/向上 + KD向上
            vol_condition = latest['Volume'] > 3000000
            macd_condition = (latest[macd_hist_col] > 0) and (latest[macd_hist_col] > prev[macd_hist_col])
            kd_condition = (latest[k_col] > latest[d_col]) and (latest[k_col] > prev[k_col])
            
            if vol_condition and macd_condition and kd_condition:
                buy_list.append({
                    "代號": pure_ticker,
                    "收盤價": float(latest['Close']),
                    "成交量(張)": int(latest['Volume'] / 1000), # 轉換為張數
                    "MACD柱狀": round(float(latest[macd_hist_col]), 2),
                    "K值": round(float(latest[k_col]), 2)
                })
        except Exception:
            continue
            
    status_text.text("掃描完成！")
    
    # 轉換成 DataFrame 並排序
    results_df = pd.DataFrame(buy_list)
    if not results_df.empty:
        # 依成交量排序，並取前 10 名
        results_df = results_df.sort_values(by="成交量(張)", ascending=False).head(10)
        # 重新設定 Index 讓表格好看
        results_df.reset_index(drop=True, inplace=True)
        results_df.index = results_df.index + 1 
        
    return results_df

# 4. 按鈕觸發事件
if st.button("🚀 開始盤後選股 (選取前10大成交量)"):
    with st.spinner('連線至資料庫中...'):
        results = run_screener(DEFAULT_STOCKS)
        
    st.subheader(f"📅 今日 ({datetime.datetime.now().strftime('%Y-%m-%d')}) 嚴選名單")
    
    if results is not None and not results.empty:
        # 在網頁上顯示漂亮的表格
        st.dataframe(results, use_container_width=True)
        st.success("✅ 提示：請從上方名單挑選題材最熱絡、型態剛突破的標的。")
    else:
        st.warning("⚠️ 今日無符合雙同向強勢條件的股票，建議現金為王。")