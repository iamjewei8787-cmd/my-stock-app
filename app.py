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
st.set_page_config(page_title="台股波段選股與回測神器", page_icon="⏱️", layout="centered")
st.title("⏱️ 台股波段選股 & 時光機回測")
st.markdown("**策略：** 排除 ETF | 成交量>1500張 | MACD 翻紅 + KD 黃金交叉")

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
        # 備用名單
        return ["2330.TW", "2317.TW", "2454.TW", "2382.TW", "3231.TW", "1519.TW", "2603.TW", "2409.TW"]
    return tickers

# ==========================================
# 3. 核心選股與回測邏輯
# ==========================================
def analyze_stock_with_backtest(ticker, target_date):
    try:
        # 為了計算指標與看未來，抓取過去 1 年的資料
        df = yf.download(ticker, period="1y", progress=False)
        if df.empty or len(df) < 50:
            return None
            
        # 移除時區資訊以便比對日期
        df.index = df.index.tz_localize(None)
        target_datetime = pd.to_datetime(target_date)
        
        # 計算技術指標 (在全部資料上計算，避免邊界效應)
        macd = df.ta.macd(fast=12, slow=26, signal=9)
        df = pd.concat([df, macd], axis=1)
        stoch = df.ta.stoch(high='High', low='Low', close='Close', k=9, d=3, smooth_k=3)
        df = pd.concat([df, stoch], axis=1)
        
        # 切割資料：找到「目標日期」當天或之前最近的交易日
        past_df = df[df.index <= target_datetime]
        if len(past_df) < 2:
            return None
            
        # 取得目標日的狀態與前一天的狀態
        latest = past_df.iloc[-1]
        prev = past_df.iloc[-2]
        signal_date = latest.name
        
        macd_hist_col = [c for c in df.columns if 'MACDh' in c][0]
        k_col = [c for c in df.columns if 'STOCHk' in c][0]
        d_col = [c for c in df.columns if 'STOCHd' in c][0]
        
        # 條件：量大(放寬至 >1500張) + MACD翻紅/向上 + KD向上
        vol_condition = latest['Volume'] > 1500000 
        macd_condition = (latest[macd_hist_col] > 0) and (latest[macd_hist_col] > prev[macd_hist_col])
        kd_condition = (latest[k_col] > latest[d_col]) and (latest[k_col] > prev[k_col])
        
        if vol_condition and macd_condition and kd_condition:
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

# 設定日曆選擇器，預設為今天
today = datetime.date.today()
selected_date = st.date_input(
    "請選擇你想驗證的日期 (例如選擇上個月的某一天)：", 
    value=today,
    max_value=today
)

if st.button(f"🚀 開始掃描 {selected_date} 的飆股並回測", type="primary"):
    
    st.info("🔄 獲取上市櫃名單中...")
    stock_list = get_all_tw_tickers()
    
    if stock_list:
        progress_bar = st.progress(0)
        status_text = st.empty()
        buy_list = []
        completed = 0
        total_stocks = len(stock_list)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            # 傳遞 selected_date 給分析函數
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
            
            st.success(f"🎯 在 **{selected_date}** 這天，全市場符合條件的前 10 大強勢股及後續表現如下：")
            st.dataframe(results_df, use_container_width=True)
            
            st.markdown("""
            **📊 報表說明：**
            * **買進價**：以訊號發生當天的收盤價計算。
            * **兩週內最高價**：買進後 14 天內，該股票觸及的最高價。
            * **潛在最大獲利(%)**：如果在最高點賣出，你能賺取的最大報酬率。*(實戰中不可能永遠賣在最高點，此數據用於評估該策略的爆發力)*。
            """)
        else:
            st.warning(f"⚠️ 在 {selected_date} 附近，全市場無符合雙同向強勢條件的股票。大盤當時可能處於弱勢。")
            st.dataframe(results_df, use_container_width=True)
            st.success("🎯 **操盤建議：** 上述為今日全市場中，符合【雙同向 + 成交量最大】的前 10 檔。請打開看盤軟體確認是否剛突破壓力區。")
        else:
            st.warning("⚠️ 今日全市場無符合雙同向強勢條件且量大的股票，大盤可能處於弱勢或震盪，建議多看少做。")
