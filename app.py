import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
import time

# --- 頁面設定 ---
st.set_page_config(page_title="台股起漲潛伏選股器", layout="wide")

st.title("🚀 台股起漲前夕：潛伏模式選股器")
st.markdown("""
本工具根據 **「均線糾結 + 縮量窒息 + 低位階」** 邏輯，篩選全台股普通股（排除 ETF）。
> **核心指標：** $5MA, 10MA, 20MA, 60MA$ 糾結、成交量極縮、股價緊貼年線。
""")

# --- 函數定義 ---

@st.cache_data(ttl=86400) # 每天更新一次清單
def get_taiwan_stock_list():
    """抓取全台股普通股清單 (排除 ETF, 權證)"""
    try:
        twse_url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        tpex_url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
        
        tickers = []
        for url, suffix in [(twse_url, ".TW"), (tpex_url, ".TWO")]:
            response = requests.get(url)
            df = pd.read_html(response.text)[0]
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            # 篩選普通股 (ESVTFR) 並排除備註不為空的股票
            mask = (df['CFICode'] == 'ESVTFR')
            valid_stocks = df[mask]['有價證券代號及名稱'].str.split('　').str[0]
            tickers.extend([t + suffix for t in valid_stocks])
        return tickers
    except Exception as e:
        st.error(f"取得股票清單失敗: {e}")
        return []

def analyze_stock(df, symbol):
    """起漲潛伏模式邏輯分析"""
    if len(df) < 240: return None
    
    latest = df.iloc[-1]
    
    # 1. 均線糾結度 (5, 10, 20, 60 MA)
    ma_vals = [latest['MA5'], latest['MA10'], latest['MA20'], latest['MA60']]
    ma_spread = (max(ma_vals) - min(ma_vals)) / min(ma_vals)
    
    # 2. 成交量窒息 (今日量 < 20日均量 40%)
    vol_ratio = latest['Volume'] / latest['V_MA20'] if latest['V_MA20'] > 0 else 1
    
    # 3. 位階與盤整 (距離 240MA 12% 內，20日振幅 10% 內)
    dist_240 = (latest['Close'] - latest['MA240']) / latest['MA240']
    
    # 設定門檻
    if ma_spread < 0.035 and vol_ratio < 0.4 and abs(dist_240) < 0.12 and latest['Amp_20'] < 0.10:
        return {
            "股票代號": symbol,
            "收盤價": round(float(latest['Close']), 2),
            "均線糾結度": f"{round(ma_spread * 100, 2)}%",
            "量能縮比": f"{round(vol_ratio * 100, 1)}%",
            "距離年線": f"{round(dist_240 * 100, 1)}%",
            "20日振幅": f"{round(latest['Amp_20'] * 100, 1)}%"
        }
    return None

# --- 主程式邏輯 ---

tickers = get_taiwan_stock_list()

if not tickers:
    st.warning("目前無法獲取股票清單，請稍後再試。")
else:
    st.sidebar.write(f"當前股票總數: {len(tickers)}")
    
    if st.button("🔍 開始全市場掃描 (需時約 5-8 分鐘)"):
        final_results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 為了提升速度，每次抓取 1 年數據
        for i, sym in enumerate(tickers):
            # 更新進度條
            pct = (i + 1) / len(tickers)
            progress_bar.progress(pct)
            if i % 50 == 0:
                status_text.text(f"正在掃描: {sym} ({i+1}/{len(tickers)})")

            try:
                # 抓取數據 (使用 period='1y' 兼顧 MA240 與速度)
                data = yf.download(sym, period="1y", progress=False, show_errors=False)
                
                if data.empty or len(data) < 240:
                    continue
                
                # 技術指標計算
                data['MA5'] = data['Close'].rolling(5).mean()
                data['MA10'] = data['Close'].rolling(10).mean()
                data['MA20'] = data['Close'].rolling(20).mean()
                data['MA60'] = data['Close'].rolling(60).mean()
                data['MA240'] = data['Close'].rolling(240).mean()
                data['V_MA20'] = data['Volume'].rolling(20).mean()
                data['Amp_20'] = (data['Close'].rolling(20).max() - data['Close'].rolling(20).min()) / data['Close'].rolling(20).min()
                
                res = analyze_stock(data, sym)
                if res:
                    final_results.append(res)
            except:
                continue
        
        status_text.text("掃描完成！")
        
        if final_results:
            st.success(f"找到 {len(final_results)} 檔符合潛伏特徵標的")
            st.dataframe(pd.DataFrame(final_results), use_container_width=True)
            st.balloons()
        else:
            st.info("今日全台股無符合「起漲潛伏」特徵標的。")

st.divider()
st.caption("註：建議選出標點後，請手動確認大戶持股比例與最新營收 YoY 是否轉正。數據由 yfinance 提供，僅供參考。")
