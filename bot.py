import os
import requests
import datetime
import random
import time
import pandas as pd
from threading import Thread
from telebot import TeleBot, types

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or "8834283543:AAHtCCajH7tktstOgE2Qdy3ZyaWaXwmGCfc"
CHAT_ID = os.getenv("CHAT_ID") or "-1004453763468"
SCAN_INTERVAL_SECONDS = 30

bot = TeleBot(TELEGRAM_TOKEN)
ACTIVE_TRADES = {}

VOL_SMA_LENGTH = 14
LEVERAGE = 50
RISK_REWARD_RATIO = 2.5

def scan_all_binance_futures():
    try:
        # একাধিক এন্ডপয়েন্ট ব্যবহার করা হচ্ছে
        urls = ["https://fapi.binance.com/fapi/v1/ticker/24hr", "https://fapi1.binance.com/fapi/v1/ticker/24hr"]
        for url in urls:
            try:
                res = requests.get(url, timeout=5).json()
                if isinstance(res, list):
                    return [t for t in res if 'symbol' in t and t['symbol'].endswith('USDT')]
            except: continue
        return []
    except Exception as e:
        print(f"[API ERROR] {e}", flush=True)
        return []

def get_klines_dataframe(symbol, timeframe, limit=100):
    try:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
        res = requests.get(url, timeout=5).json()
        df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base', 'taker_quote', 'ignore'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df
    except: return None

def detect_pattern(df):
    c = df.iloc[-2]
    p = df.iloc[-3]
    
    # ভলিউম কন্ডিশন (আপনার রিকোয়েস্ট অনুযায়ী)
    vol_sma = df['volume'].rolling(window=VOL_SMA_LENGTH).mean().iloc[-2]
    if c['volume'] <= vol_sma:
        return None, None
        
    # সিম্পল প্যাটার্ন ডিটেকশন
    if c['close'] > c['open'] and p['open'] > p['close']:
        return "Bullish Reversal", "Buy"
    if c['close'] < c['open'] and p['close'] > p['open']:
        return "Bearish Reversal", "Sell"
        
    return None, None

def auto_signal_generator_loop():
    while True:
        coins = scan_all_binance_futures()
        random.shuffle(coins)
        for coin in coins[:5]:
            symbol = coin['symbol']
            base = symbol.replace("USDT", "")
            if base in ACTIVE_TRADES: continue
            
            df = get_klines_dataframe(symbol, "1m", limit=30)
            if df is None: continue
            
            pattern, action = detect_pattern(df)
            if action:
                msg = f"🚀 **Signal: {base}**\nAction: {action}\nTime: {datetime.datetime.now().strftime('%H:%M:%S')}"
                bot.send_message(CHAT_ID, msg, parse_mode='Markdown')
                ACTIVE_TRADES[base] = True
        time.sleep(SCAN_INTERVAL_SECONDS)

# বট রান করা
if __name__ == '__main__':
    Thread(target=auto_signal_generator_loop, daemon=True).start()
    bot.infinity_polling()
