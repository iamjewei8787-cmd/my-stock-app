import yfinance as yf
import pandas as pd
import requests
from datetime import datetime

def get_taiwan_stock_list():
    """
    從證交所抓取所有上市與上櫃股票清單，並排除 ETF 與權證
    """
    print("正在獲取全台股清單，請稍候...")
    
    # 上市股票清單網址
    twse_url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    # 上櫃股票清單網址
    tpex_url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    
    tickers = []
    
    for url, suffix in [(twse_url, ".TW"), (tpex_url, ".TWO")]:
        response = requests.get(url)
        # 使用 pandas 讀取網頁表格
        df = pd.read_html(response.text)[0]
        # 整理格式
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        
        # 關鍵篩選：
        # 1. 排除 ETF (通常分類為 '股票' 以外的，或是代碼為 00 開頭)
        # 2. CFICode 必須為 'ESVTFR' (代表普通股)
        # 3. 過濾掉權證、特別股等
        mask = (df['CFICode'] == 'ESVTFR') & (df['備註'].isna())
        valid_stocks = df[mask]['有價證券代號及名稱'].str.split('　').str[0]
        
        tickers.extend([t + suffix for t in valid_stocks])
    
    print(f"成功獲取 {len(tickers)} 檔普通股標的。")
    return tickers

def calculate_indicators(df):
    """ 計算技術指標 """
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['MA240'] = df['Close'].rolling(240).mean()
    df['V_MA20'] = df['Volume'].rolling(20).mean()
    
    # 20日振幅
    df['Max_20'] = df['Close'].rolling(20).max()
    df['Min_20'] = df['Close'].rolling(20).min()
    df['Amp_20'] = (df['Max_20'] - df['Min_20']) / df['Min_20']
    return df

def scan_logic(df, symbol):
    """ 潛伏模式核心邏輯 """
    if len(df) < 240 or df['Volume'].iloc[-1] == 0: return None
    
    latest = df.iloc[-1]
    
    # 1. 均線糾結 (5, 10, 20, 60MA 差距 < 3.5%)
    ma_vals = [latest['MA5'], latest['MA10'], latest['MA20'], latest['MA60']]
    ma_spread = (max(ma_vals) - min(ma_vals)) / min(ma_vals)
    
    # 2. 成交量窒息 (今日量 < 20日均量 40%)
    vol_ratio = latest['Volume'] / latest['V_MA20']
    
    # 3. 位階與盤整
    dist_240 = (latest['Close'] - latest['MA240']) / latest['MA240']
    
    # 最終篩選門檻
    if ma_spread < 0.035 and vol_ratio < 0.4 and abs(dist_240) < 0.12 and latest['Amp_20'] < 0.10:
        return {
            "代號": symbol,
            "收盤價": round(latest['Close'], 2),
            "均線糾結": f"{round(ma_spread*100, 1)}%",
            "量能縮比": f"{round(vol_ratio*100, 1)}%",
            "位階(240MA)": f"{round(dist_240*100, 1)}%"
        }
    return None

# --- 主程式執行 ---
if __name__ == "__main__":
    all_tickers = get_taiwan_stock_list()
    final_list = []
    
    print(f"--- 開始掃描全市場 ({datetime.now().strftime('%Y-%m-%d')}) ---")
    
    # 為了避免掃描太慢，這裡使用循環，你也可以加上進度條
    count = 0
    for sym in all_tickers:
        count += 1
        if count % 100 == 0: print(f"已掃描 {count} 檔...")
        
        # 抓取最近 1 年數據即可
        try:
            data = yf.download(sym, period="1y", progress=False, show_errors=False)
            if not data.empty:
                data = calculate_indicators(data)
                res = scan_logic(data, sym)
                if res:
                    final_list.append(res)
        except:
            continue

    print("\n" + "="*30)
    if final_list:
        result_df = pd.DataFrame(final_list)
        print(f"掃描完畢！共發現 {len(final_list)} 檔符合潛伏特徵之標的：")
        print(result_df.to_string(index=False))
    else:
        print("今日全市場無符合「起漲前潛伏」特徵之標的。")
    print("="*30)
