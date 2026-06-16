import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# --- 1. WEB APP INTERFACE CONFIGURATION ---
st.set_page_config(page_title="Binary Signal Engine", layout="wide", page_icon="📈")

st.markdown("""
    <style>
    .main .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    h1 {margin-bottom: 0px;}
    </style>
""", unsafe_allow_html=True)

st.title("🎯 Live Binary Options Signal Dashboard")
st.caption("A standalone real-time algorithmic charting engine with automated multi-expiration confidence scoring.")

# --- 2. CONTROL SIDEBAR PANEL ---
st.sidebar.header("🕹️ Dashboard Control Engine")
asset_display = st.sidebar.selectbox(
    "Select Target Asset", 
    ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "Bitcoin (BTC/USD)"]
)

# Map human-readable names to Yahoo Finance system tickers
ticker_map = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "AUD/USD": "AUDUSD=X",
    "Bitcoin (BTC/USD)": "BTC-USD"
}
asset = ticker_map[asset_display]

timeframe = st.sidebar.selectbox("Analysis Timeframe", ["1m", "5m", "15m"], index=1)
period = "2d" if timeframe != "1m" else "1d"

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Strategy Weights")
w_trend = st.sidebar.slider("Trend Alignment Weight", 0, 50, 30)
w_rsi = st.sidebar.slider("RSI Momentum Weight", 0, 50, 30)
w_bb = st.sidebar.slider("Bollinger Band Weight", 0, 50, 20)
w_vol = st.sidebar.slider("Volume Validation Weight", 0, 50, 20)

# Real-time mathematical protection check
total_weight = w_trend + w_rsi + w_bb + w_vol
if total_weight != 100:
    st.sidebar.error(f"❌ Weights add up to {total_weight}%. Readjust them to equal exactly 100%!")

# --- 3. LOW-LATENCY DATA FETCHING ---
@st.cache_data(ttl=15)  # Fast cache refresh rate for live trading tracking
def fetch_live_web_data(ticker, tf, per):
    try:
        df = yf.download(tickers=ticker, period=per, interval=tf, progress=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        return df
    except:
        return None

df = fetch_live_web_data(asset, timeframe, period)

if df is None or len(df) < 30:
    st.error("Error connecting to live market feeds. Please refresh or pick an alternate asset pair.")
    st.stop()

# --- 4. MATHEMATICAL INDICATOR ENGINE ---
def compute_indicators(data):
    d = data.copy()
    # Trend indicators
    d['EMA20'] = d['Close'].ewm(span=20, adjust=False).mean()
    d['EMA50'] = d['Close'].ewm(span=50, adjust=False).mean()
    
    # RSI Momentum calculation
    delta = d['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(span=14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(span=14, adjust=False).mean()
    rs = gain / (loss + 1e-9)
    d['RSI'] = 100 - (100 / (1 + rs))
    
    # Volatility bands
    d['MA20'] = d['Close'].rolling(window=20).mean()
    d['StdDev'] = d['Close'].rolling(window=20).std()
    d['BB_Upper'] = d['MA20'] + (2 * d['StdDev'])
    d['BB_Lower'] = d['MA20'] - (2 * d['StdDev'])
    
    # Volatility execution analysis
    high_low = d['High'] - d['Low']
    high_cp = (d['High'] - d['Close'].shift()).abs()
    low_cp = (d['Low'] - d['Close'].shift()).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    d['ATR'] = tr.rolling(window=14).mean()
    d['VolMA'] = d['Volume'].rolling(window=10).mean()
    
    return d

df = compute_indicators(df)
latest = df.iloc[-1]
prev = df.iloc[-2]

# --- 5. SIGNAL PROCESSING & CONFIDENCE GENERATOR ---
score = 0
direction = "NEUTRAL"
reasons = []

# Core Logic 1: Trend Alignment Vector
if latest['Close'] > latest['EMA20'] and latest['EMA20'] > latest['EMA50']:
    trend_dir = "CALL"
    score += w_trend
    reasons.append(f"Bullish Trend Framework verified (+{w_trend} pts)")
elif latest['Close'] < latest['EMA20'] and latest['EMA20'] < latest['EMA50']:
    trend_dir = "PUT"
    score += w_trend
    reasons.append(f"Bearish Trend Framework verified (+{w_trend} pts)")
else:
    trend_dir = "NEUTRAL"
    reasons.append("Market moving sideways, trend filter skipped (+0 pts)")

# Core Logic 2: RSI Momentum Oscillations
if latest['RSI'] < 30:
    direction = "CALL"
    score += w_rsi
    reasons.append(f"RSI Oversold structural rejection zone (+{w_rsi} pts)")
elif latest['RSI'] > 70:
    direction = "PUT"
    score += w_rsi
    reasons.append(f"RSI Overbought structural exhaustion zone (+{w_rsi} pts)")
else:
    if latest['RSI'] > prev['RSI'] and trend_dir == "CALL":
        direction = "CALL"
        score += int(w_rsi * 0.5)
        reasons.append(f"RSI climbing with active volume momentum (+{int(w_rsi * 0.5)} pts)")
    elif latest['RSI'] < prev['RSI'] and trend_dir == "PUT":
        direction = "PUT"
        score += int(w_rsi * 0.5)
        reasons.append(f"RSI falling with active volume momentum (+{int(w_rsi * 0.5)} pts)")

# Core Logic 3: Bollinger Band Extremes
if latest['Close'] <= latest['BB_Lower'] and direction == "CALL":
    score += w_bb
    reasons.append(f"Price piercing extreme lower Bollinger Band boundary (+{w_bb} pts)")
elif latest['Close'] >= latest['BB_Upper'] and direction == "PUT":
    score += w_bb
    reasons.append(f"Price piercing extreme upper Bollinger Band boundary (+{w_bb} pts)")

# Core Logic 4: Volume Validation
if latest['Volume'] > latest['VolMA']:
    score += w_vol
    reasons.append(f"High transactional volume breakout confirmed (+{w_vol} pts)")

# Handle calculations safely
score = min(int(score), 100)
if direction == "NEUTRAL" or total_weight != 100:
    score = 0

# Expiration Assignment Engine via Average True Range (ATR)
atr_baseline = df['ATR'].rolling(30).mean().iloc[-1]
if latest['ATR'] > atr_baseline:
    rec_exp = "1 - 3 Minutes (High Volatility Breakout)"
else:
    rec_exp = "5 - 15 Minutes (Mean Reversion / Trend Ride)"

# --- 6. METRIC PRESENTATION LAYER ---
col1, col2, col3 = st.columns([1, 1, 1.2])

with col1:
    st.metric(label="Active Asset Class", value=asset_display)
    if direction == "CALL" and score > 0:
        st.markdown("<h2 style='color:#2ecc71; margin-top:0;'>🟢 CALL (BUY)</h2>", unsafe_allow_html=True)
    elif direction == "PUT" and score > 0:
        st.markdown("<h2 style='color:#e74c3c; margin-top:0;'>🔴 PUT (SELL)</h2>", unsafe_allow_html=True)
    else:
        st.markdown("<h2 style='color:#95a5a6; margin-top:0;'>⚪ MONITORING</h2>", unsafe_allow_html=True)

with col2:
    st.metric(label="Target Expiration Window", value=rec_exp)
    if score >= 75:
        bg, msg = "#2ecc71", "HIGH ACCURACY SETUP"
    elif score >= 50:
        bg, msg = "#f1c40f", "MODERATE SETUP"
    else:
        bg, msg = "#e74c3c", "NO TRADE / FILTER ACTIVE"
        
    st.markdown(f"""
    <div style='background-color:{bg}; padding:12px; border-radius:6px; text-align:center;'>
        <h3 style='color:white; margin:0; font-size: 22px;'>Score: {score}%</h3>
        <strong style='color:white; font-size: 11px;'>{msg}</strong>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown("**Algorithmic Confluence Log**")
    for r in reasons:
        st.markdown(f"<span style='font-size:13px;'>✔️ {r}</span>", unsafe_allow_html=True)

st.markdown("---")

# --- 7. PLOTLY VISUAL INTERACTIVE LAYER ---
st.subheader(f"📊 Live Technical Charting Feed ({timeframe})")

fig = go.Figure(data=[go.Candlestick(
    x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
    name='Market Data', increasing_line_color='#2ecc71', decreasing_line_color='#e74c3c'
)])

# Add strategy lines to visual frame
fig.add_trace(go.Scatter(x=df.index, y=df['EMA20'], name='EMA 20', line=dict(color='#f39c12', width=1.5)))
fig.add_trace(go.Scatter(x=df.index, y=df['EMA50'], name='EMA 50', line=dict(color='#3498db', width=1.5)))
fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], name='Upper Band', line=dict(color='rgba(231,76,60,0.4)', dash='dot')))
fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], name='Lower Band', line=dict(color='rgba(46,204,113,0.4)', dash='dot')))

fig.update_layout(
    xaxis_rangeslider_visible=False,
    height=500,
    margin=dict(l=30, r=30, t=10, b=10),
    template="plotly_dark",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

st.plotly_chart(fig, use_container_width=True)
st.caption(f"Engine heartbeat ping active • Last data calculation: {datetime.now().strftime('%H:%M:%S')} Local Time")
