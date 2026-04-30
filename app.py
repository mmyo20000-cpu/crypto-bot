import streamlit as st
import ccxt
import pandas as pd
import time
import hmac
import numpy as np

# ========== 1. الحماية بباسوورد ==========
def check_password():
    def password_entered():
        if hmac.compare_digest(st.session_state["password"], "950398@Bot"): # غير الباسوورد
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.title("🔒 تسجيل دخول البوت")
    st.text_input("كلمة السر", type="password", on_change=password_entered, key="password")
    if "password_correct" in st.session_state:
        st.error("كلمة السر غلط")
    return False

if not check_password():
    st.stop()

# ========== 2. دالة حساب RSI ==========
def calculate_rsi(data, period=14):
    delta = data['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

# ========== 3. إعدادات البوت ==========
st.set_page_config(page_title="Crypto Bot Pro", layout="wide")
st.title("🤖 بوت تداول RSI + وقف خسارة")

# مفاتيح Testnet - بنحطها في Secrets بعدين
API_KEY = st.secrets["BINANCE_API_KEY"]
SECRET_KEY = st.secrets["BINANCE_SECRET_KEY"]

exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'},
})
exchange.set_sandbox_mode(True) # تجريبي

# ========== 4. الواجهة ==========
tab1, tab2, tab3 = st.tabs(["📊 لوحة التحكم", "⚙️ الإعدادات", "📜 سجل الصفقات"])

with tab2:
    st.subheader("إعدادات الاستراتيجية")
    col1, col2 = st.columns(2)
    symbol = col1.selectbox("العملة", ['BTC/USDT', 'ETH/USDT'])
    amount_usdt = col2.number_input("مبلغ كل صفقة USDT", 10, 1000, 20)

    st.subheader("إعدادات RSI")
    col3, col4 = st.columns(2)
    rsi_buy = col3.slider("اشتر لو RSI تحت", 10, 40, 30)
    rsi_sell = col4.slider("بيع لو RSI فوق", 60, 90, 70)

    st.subheader("إدارة المخاطر 🔒")
    col5, col6, col7 = st.columns(3)
    stop_loss_pct = col5.number_input("وقف خسارة %", 1.0, 10.0, 3.0, 0.5)
    take_profit_pct = col6.number_input("جني أرباح %", 1.0, 20.0, 5.0, 0.5)
    update_interval = col7.slider("افحص السوق كل كم ثانية", 20, 300, 60)

with tab1:
    if 'bot_running' not in st.session_state:
        st.session_state.bot_running = False
        st.session_state.trades = []
        st.session_state.entry_price = 0

    col1, col2, col3 = st.columns(3)
    if col1.button("تشغيل البوت", type="primary"):
        st.session_state.bot_running = True
    if col2.button("إيقاف البوت"):
        st.session_state.bot_running = False
        st.session_state.entry_price = 0
    if col3.button("مسح السجل"):
        st.session_state.trades = []

    placeholder = st.empty()

    while st.session_state.bot_running:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=100)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            current_rsi = calculate_rsi(df)
            current_price = df['close'].iloc[-1]

            balance = exchange.fetch_balance()
            usdt_balance = balance['USDT']['free']
            coin = symbol.split('/')[0]
            coin_balance = balance[coin]['free'] if coin in balance else 0

            action = "انتظار"

            if current_rsi < rsi_buy and usdt_balance > amount_usdt and st.session_state.entry_price == 0:
                qty = amount_usdt / current_price
                order = exchange.create_market_buy_order(symbol, qty)
                st.session_state.entry_price = current_price
                action = f"✅ شراء {qty:.5f} {coin} @ {current_price:,.2f}"
                st.session_state.trades.append(f"{time.strftime('%H:%M:%S')} | شراء | {qty:.5f} {coin} @ {current_price:,.2f}")

            elif coin_balance > 0.00001 and st.session_state.entry_price > 0:
                pnl_pct = ((current_price - st.session_state.entry_price) / st.session_state.entry_price) * 100

                sell_reason = ""
                if current_rsi > rsi_sell:
                    sell_reason = "RSI عالي"
                elif pnl_pct <= -stop_loss_pct:
                    sell_reason = f"وقف خسارة {pnl_pct:.2f}%"
                elif pnl_pct >= take_profit_pct:
                    sell_reason = f"جني أرباح {pnl_pct:.2f}%"

                if sell_reason:
                    order = exchange.create_market_sell_order(symbol, coin_balance)
                    action = f"💰 بيع {coin_balance:.5f} {coin} | السبب: {sell_reason}"
                    st.session_state.trades.append(f"{time.strftime('%H:%M:%S')} | بيع | {coin_balance:.5f} {coin} @ {current_price:,.2f} | {sell_reason}")
                    st.session_state.entry_price = 0

            with placeholder.container():
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("السعر", f"{current_price:,.2f}")
                c2.metric("RSI", f"{current_rsi:.2f}")
                c3.metric("رصيد USDT", f"{usdt_balance:.2f}")

                if st.session_state.entry_price > 0:
                    pnl_pct = ((current_price - st.session_state.entry_price) / st.session_state.entry_price) * 100
                    c4.metric("الربح/الخسارة", f"{pnl_pct:.2f}%", delta=f"{pnl_pct:.2f}%")
                else:
                    c4.metric("الحالة", "لا توجد صفقة")

                st.info(f"آخر إجراء: {action}")
                st.caption(f"سعر الدخول: {st.session_state.entry_price:,.2f} | 🟢 شغال | تحديث: {time.strftime('%H:%M:%S')}")

            time.sleep(update_interval)

        except Exception as e:
            st.error(f"خطأ: {e}")
            st.session_state.bot_running = False

with tab3:
    st.subheader("سجل آخر 20 صفقة")
    if st.session_state.trades:
        for trade in reversed(st.session_state.trades[-20:]):
            st.text(trade)
    else:
        st.info("مافي صفقات للحين")
