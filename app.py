import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import datetime
import concurrent.futures
import requests

# ==========================================
# 1. 介面設定
# ==========================================
st.set_page_config(page_title="台股波段選股神器", page_icon="📈", layout="centered")
st.title("📈 台股波段選股神器 (全市場掃描版)")
st.markdown("**策略：** 掃描全台股上市/上櫃 | 排除 ETF | MACD 翻紅 + KD 黃金交叉 | 依成交量排行")

# ==========================================
# 2. 自動抓取全台股代號 (使用政府 Open API)
# ==========================================
@st.cache_data(ttl=86400) # 每天只抓一次名單，減少伺服器負擔
def get_all_tw_tickers():
    tickers = []
    try:
        # 1. 抓取上市股票 (使用證交所 Open API)
        twse_url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        res_twse = requests.get(twse_url, timeout=10)
        for item in res_twse.json():
            code = item.get('Code', '')
            # 篩選 4 位數字代號，且排除 00 開頭的 ETF
            if len(code) == 4 and code.isdigit() and not code.startswith('00'):
                tickers.append(f"{code}.TW")
                
        # 2. 抓取上櫃股票 (使用櫃買中心 Open API)
        tpex_url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
        res_tpex = requests.get(tpex_url, timeout=10)
        for item in res_tpex.json():
            code = item.get('SecuritiesCompanyCode', '')
            if len(code) == 4 and code.isdigit() and not code.startswith('00'):
                tickers.append(f"{code}.TWO")
                
    except Exception as e:
        # 終極防呆機制：如果政府 API 剛好在維護，載入備用熱門股名單確保 App 不會崩潰
        return [
            "2330.TW", "2317.TW", "2454.TW", "2382.TW", "3231.TW", "2308.TW", "1519.TW", 
            "1514.TW", "2356.TW", "5371.TWO", "2603.TW", "2609.TW", "2615.TW", "3481.TW", 
            "2409.TW", "2303.TW", "2881.TW", "2882.TW", "2891.TW", "2324.TW", "2376.TW", 
            "3037.TW", "8046.TW", "3189.TW", "6274.TWO", "3017.TW", "2368.TW"
        ]
        
    return tickers

# ==========================================
# 3. 單一股票的技術分析邏輯
# ==========================================
def analyze_stock(ticker):
    try:
        # 抓取近半年資料
        df = yf.download(ticker, period="6mo", progress=False)
        if df.empty or len(df) < 50:
            return None
            
        # 計算技術指標
        macd = df.ta.macd(fast=12, slow=26, signal=9)
        df = pd.concat([df, macd], axis=1)
        stoch = df.ta.stoch(high='High', low='Low', close='Close', k=9, d=3, smooth_k=3)
        df = pd.concat([df, stoch], axis=1)
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        macd_hist_col = [c for c in df.columns if 'MACDh' in c][0]
        k_col = [c for c in df.columns if 'STOCHk' in c][0]
        d_col = [c for c in df.columns if 'STOCHd' in c][0]
        
        # 條件：量大(>3000張) + MACD翻紅/向上 + KD向上
        vol_condition = latest['Volume'] > 3000000
        macd_condition = (latest[macd_hist_col] > 0) and (latest[macd_hist_col] > prev[macd_hist_col])
        kd_condition = (latest[k_col] > latest[d_col]) and (latest[k_col] > prev[k_col])
        
        if vol_condition and macd_condition and kd_condition:
            pure_ticker = ticker.split('.')[0]
            return {
                "代號": pure_ticker,
                "收盤價": float(latest['Close']),
                "成交量(張)": int(latest['Volume'] / 1000),
                "MACD柱狀": round(float(latest[macd_hist_col]), 2),
                "K值": round(float(latest[k_col]), 2)
            }
    except Exception:
        return None
    return None

# ==========================================
# 4. 介面互動與多執行緒掃描區塊
# ==========================================
if st.button("🚀 啟動全市場掃描 (需時約 1-2 分鐘)", type="primary"):
    
    st.info("🔄 正在連線至政府 Open API 獲取最新上市櫃名單...")
    stock_list = get_all_tw_tickers()
    
    if not stock_list:
        st.error("❌ 無法獲取股票名單，請稍後再試。")
    else:
        st.success(f"✅ 成功獲取 {len(stock_list)} 檔股票，開始高速分析...")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        buy_list = []
        
        # 使用多執行緒加速下載 (同時處理 15 檔股票)
        completed = 0
        total_stocks = len(stock_list)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            # 提交所有任務
            future_to_ticker = {executor.submit(analyze_stock, ticker): ticker for ticker in stock_list}
            
            # 收集結果並更新進度條
            for future in concurrent.futures.as_completed(future_to_ticker):
                completed += 1
                if completed % 10 == 0 or completed == total_stocks:
                    progress_bar.progress(completed / total_stocks)
                    status_text.text(f"掃描進度: {completed} / {total_stocks} 檔...")
                
                result = future.result()
                if result:
                    buy_list.append(result)
        
        status_text.text("✨ 掃描完成！")
        
        # 整理結果並排序
        results_df = pd.DataFrame(buy_list)
        if not results_df.empty:
            results_df = results_df.sort_values(by="成交量(張)", ascending=False).head(10)
            results_df.reset_index(drop=True, inplace=True)
            results_df.index = results_df.index + 1
            
            st.subheader(f"📅 今日 ({datetime.datetime.now().strftime('%Y-%m-%d')}) 嚴選爆發潛力股")
            st.dataframe(results_df, use_container_width=True)
            st.success("🎯 **操盤建議：** 上述為今日全市場中，符合【雙同向 + 成交量最大】的前 10 檔。請打開看盤軟體確認是否剛突破壓力區。")
        else:
            st.warning("⚠️ 今日全市場無符合雙同向強勢條件且量大的股票，大盤可能處於弱勢或震盪，建議多看少做。")
