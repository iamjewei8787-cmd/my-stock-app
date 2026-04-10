import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import datetime
import concurrent.futures
import requests

# 1. 介面設定
st.set_page_config(page_title="台股波段選股神器", page_icon="📈", layout="centered")
st.title("📈 台股波段選股神器 (全市場掃描版)")
st.markdown("**策略：** 掃描全台股上市/上櫃 | 排除 ETF | MACD 翻紅 + KD 黃金交叉 | 依成交量排行")

# 2. 自動抓取全台股代號 (加入 Cache 避免重複抓取被封鎖)
@st.cache_data(ttl=86400) # 每天只抓一次名單
def get_all_tw_tickers():
    tickers = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    # 證交所(上市)與櫃買中心(上櫃)的公開資料網址
    urls = {
        ".TW": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
        ".TWO": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    }
    
    for suffix, url in urls.items():
        try:
            res = requests.get(url, headers=headers)
            res.encoding = 'big5'
            df = pd.read_html(res.text)[0]
            
            # 清洗資料：取得代號欄位
            df.columns = df.iloc[0]
            df = df.iloc[2:]
            # 分割代號與名稱 (注意這裡的空白是全形空白)
            df['代號'] = df['有價證券代號及名稱'].astype(str).str.split('　').str[0]
            
            # 嚴格篩選：只要 4 位數字的代號 (排除權證、特別股，排除 00 開頭的 ETF)
            valid_stocks = df[df['代號'].str.match(r'^[1-9]\d{3}$')]
            tickers.extend([f"{t}{suffix}" for t in valid_stocks['代號']])
            
        except Exception as e:
            continue
            
    return tickers

# 3. 單一股票的分析邏輯
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

# 4. 介面與多執行緒執行區塊
if st.button("🚀 啟動全市場掃描 (需時約 1-2 分鐘)", type="primary"):
    
    st.info("🔄 正在連線至證交所獲取最新上市櫃名單...")
    stock_list = get_all_tw_tickers()
    
    if not stock_list:
        st.error("❌ 無法獲取股票名單，請稍後再試。")
    else:
        st.success(f"✅ 成功獲取 {len(stock_list)} 檔股票，開始分析...")
        
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
            st.success("🎯 **操盤建議：** 上述為今日全市場中，符合【雙同向 + 成交量最大】的前 10 檔。請打開 K 線圖確認是否剛突破壓力區。")
        else:
            st.warning("⚠️ 今日全市場無符合雙同向強勢條件且量大的股票，大盤可能處於弱勢或震盪，建議多看少做。")
