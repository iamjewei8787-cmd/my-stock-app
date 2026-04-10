import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import concurrent.futures
import requests

# ==========================================
# 1. 介面設定
# ==========================================
st.set_page_config(page_title="台股波段選股與回測神器", page_icon="⏱️", layout="centered")
st.title("⏱️ 台股波段選股 (除錯測試版)")
st.markdown("**測試策略：** 排除 ETF | **【僅保留】成交量 > 500 張** (無技術指標限制)")

# ==========================================
# 2. 自動抓取全台股代號 (政府 Open API)
# ==========================================
@st.cache_data(ttl=86400)
def get_all_tw_tickers():
    tickers = []
    try:
        twse_url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        res_twse = requests.get(twse_url, timeout=10)
        for item in res_twse.json():
            code = item.get('Code', '')
            if len(code) == 4 and code.isdigit() and not code.startswith('00'):
                tickers.append(f"{code}.TW")
                
        tpex_url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
        res_tpex = requests.get(tpex_url, timeout=10)
        for item in res_tpex.json():
            code = item.get('SecuritiesCompanyCode', '')
            if len(code) == 4 and code.isdigit() and not code.startswith('00'):
                tickers.append(f"{code}.TWO")
    except Exception:
        return ["2330.TW", "2317.TW", "2454.TW", "2382.TW", "3231.TW", "1519.TW", "2603.TW", "2409.TW"]
    return tickers

# ==========================================
# 3. 核心選股與回測邏輯 (純看成交量)
# ==========================================
def analyze_stock_with_backtest(ticker, target_date):
    try:
        # 抓取過去 1 年的資料
        df = yf.download(ticker, period="1y", progress=False)
        if df.empty or len(df) < 2:
            return None
            
        # 移除時區資訊以便比對日期
        df.index = df.index.tz_localize(None)
        target_datetime = pd.to_datetime(target_date)
        
        # 切割資料：找到「目標日期」當天或之前最近的交易日
        past_df = df[df.index <= target_datetime]
        if len(past_df) < 1:
            return None
            
        # 取得目標日的狀態
        latest = past_df.iloc[-1]
        signal_date = latest.name
        
        # ----------------------------------------------------
        # 🌟 唯一濾網：成交量 > 500 張 (500,000 股)
        # ----------------------------------------------------
        vol_condition = latest['Volume'] > 500000 
        
        # 只要符合成交量，就直接錄取！(拔除 MACD 與 KD 判斷)
        if vol_condition:
            entry_price = float(latest['Close'])
            pure_ticker = ticker.split('.')[0]
            
            result_dict = {
                "代號": pure_ticker,
                "訊號日期": signal_date.strftime('%Y-%m-%d'),
                "買進價(收盤)": round(entry_price, 2),
                "成交量(張)": int(latest['Volume'] / 1000)
            }
            
            # --- 🔮 偷看未來：計算未來兩週(14天)的最大利潤 ---
            future_end_date = signal_date + pd.Timedelta(days=14)
            future_df = df[(df.index > signal_date) & (df.index <= future_end_date)]
            
            if not future_df.empty:
                max_high = float(future_df['High'].max())
                max_profit_pct = ((max_high - entry_price) / entry_price) * 100
                result_dict["兩週內最高價"] = round(max_high, 2)
                result_dict["潛在最大獲利(%)"] = f"{round(max_profit_pct, 2)}%"
            else:
                result_dict["兩週內最高價"] = "尚無資料"
                result_dict["潛在最大獲利(%)"] = "尚無資料"
                
            return result_dict
            
    except Exception:
        return None
    return None

# ==========================================
# 4. 介面互動與執行
# ==========================================
st.write("---")
st.subheader("🗓️ 選擇你的時光機日期")

today = datetime.date.today()
selected_date = st.date_input(
    "請選擇你想驗證的日期：", 
    value=today,
    max_value=today
)

if st.button(f"🚀 開始測試 {selected_date} 的成交量名單", type="primary"):
    
    st.info("🔄 獲取上市櫃名單中...")
    stock_list = get_all_tw_tickers()
    
    if stock_list:
        progress_bar = st.progress(0)
        status_text = st.empty()
        buy_list = []
        completed = 0
        total_stocks = len(stock_list)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            future_to_ticker = {executor.submit(analyze_stock_with_backtest, ticker, selected_date): ticker for ticker in stock_list}
            
            for future in concurrent.futures.as_completed(future_to_ticker):
                completed += 1
                if completed % 10 == 0 or completed == total_stocks:
                    progress_bar.progress(completed / total_stocks)
                    status_text.text(f"時光機掃描進度: {completed} / {total_stocks} 檔...")
                
                result = future.result()
                if result:
                    buy_list.append(result)
        
        status_text.text("✨ 掃描與回測完成！")
        
        results_df = pd.DataFrame(buy_list)
        if not results_df.empty:
            # 依成交量排序取前 10 名
            results_df = results_df.sort_values(by="成交量(張)", ascending=False).head(10)
            results_df.reset_index(drop=True, inplace=True)
            results_df.index = results_df.index + 1
            
            st.success(f"🎯 在 **{selected_date}** 這天，全市場成交量最大的前 10 檔個股如下：")
            st.dataframe(results_df, use_container_width=True)
            
        else:
            st.error(f"⚠️ 嚴重異常：在 {selected_date} 找不到任何大於 500 張的股票。這代表資料庫連線或 API 有問題，而非策略問題。")
