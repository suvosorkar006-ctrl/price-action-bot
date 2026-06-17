import os
import requests
import datetime
import pypdf
import random
import logging
import time
import numpy as np
import pandas as pd
from threading import Thread
from telebot import TeleBot, types

logging.getLogger("pypdf").setLevel(logging.ERROR)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or "8834283543:AAHtCCajH7tktstOgE2Qdy3ZyaWaXwmGCfc"
CHAT_ID = os.getenv("CHAT_ID") or "-1004453763468"
SCAN_INTERVAL_SECONDS = 30

bot = TeleBot(TELEGRAM_TOKEN)
PDF_DATABASE = ""
ACTIVE_TRADES = {}

# বটের ইনপুট প্যারামিটারস (কনফিগারেশন)
VOL_SMA_LENGTH = 14     # আপনার চাহিদা অনুযায়ী ভলিউম SMA দৈর্ঘ্য ১৪ রাখা হলো
LEVERAGE = 50           
RISK_REWARD_RATIO = 2.5 

# উন্নত স্ট্যাটিস্টিকস ডাটাবেজ
STATS_DB = {
    "1m": {
        "today": {"signals": 0, "tp_hit": 0, "sl_hit": 0, "pnl": 0.0},
        "weekly": {"signals": 0, "tp_hit": 0, "sl_hit": 0, "pnl": 0.0},
        "monthly": {"signals": 0, "tp_hit": 0, "sl_hit": 0, "pnl": 0.0},
    },
    "5m": {
        "today": {"signals": 0, "tp_hit": 0, "sl_hit": 0, "pnl": 0.0},
        "weekly": {"signals": 0, "tp_hit": 0, "sl_hit": 0, "pnl": 0.0},
        "monthly": {"signals": 0, "tp_hit": 0, "sl_hit": 0, "pnl": 0.0},
    }
}

def set_bot_commands():
    try:
        commands = [
            types.BotCommand("start", "বট মেইন মেনু"),
            types.BotCommand("report_1m", "১ মিনিটের সিগনাল রিপোর্ট (D/W/M)"),
            types.BotCommand("report_5m", "৫ মিনিটের সিগনাল রিপোর্ট (D/W/M)"),
            types.BotCommand("signals", "বর্তমানে চলমান লাইভ সিগনাল"),
            types.BotCommand("status", "বটের বর্তমান স্ট্যাটাস"),
            types.BotCommand("close", "ম্যানুয়াল ক্লোজ (উদা: /close SOL)")
        ]
        bot.set_my_commands(commands)
        print("[INIT] Bot commands set successfully.", flush=True)
    except Exception as e:
        print(f"[INIT ERROR] Failed to set commands: {e}", flush=True)

def load_pdf_from_telegram_channel():
    global PDF_DATABASE
    PDF_DATABASE = "SFP S/R_Flip Double_Bottom Double_Top Bullish_Flag Bearish_Flag"

def scan_all_binance_futures():
    try:
        res = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=10).json()
        return [t for t in res if t['symbol'].endswith('USDT')]
    except Exception as e:
        print(f"[API ERROR] Binance 24hr ticker failed: {e}", flush=True)
        return []

def filter_scalping_coins(all_coins):
    valid = []
    random.shuffle(all_coins)
    for coin in all_coins:
        if abs(float(coin.get('priceChangePercent', 0))) >= 0.5 and float(coin.get('volume', 0)) > 200000:
            valid.append(coin)
            if len(valid) >= 5:
                break
    return valid

def get_klines_dataframe(symbol, timeframe, limit=500):
    try:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
        res = requests.get(url, timeout=5).json()
        df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base', 'taker_quote', 'ignore'])
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        return df
    except Exception as e:
        print(f"[API ERROR] Failed to fetch klines for {symbol}: {e}", flush=True)
        return None

def calculate_indicators(df):
    # শুধুমাত্র ভলিউম SMA ১৪ ক্যালকুলেট করা হচ্ছে, অন্য কোনো প্রাইস MA রাখা হয়নি
    df['Vol_SMA'] = df['volume'].rolling(window=VOL_SMA_LENGTH).mean()
    return df

def detect_chart_patterns(df):
    if len(df) < 100:
        return None, "Neutral", None
        
    c = df.iloc[-2]  
    p = df.iloc[-3]  
    
    body = abs(c['close'] - c['open'])
    upper_wick = c['high'] - max(c['open'], c['close'])
    lower_wick = min(c['open'], c['close']) - c['low']
    
    recent_df = df.iloc[-100:-1]
    peaks = []
    troughs = []
    for i in range(2, len(recent_df)-2):
        if recent_df.iloc[i]['high'] > recent_df.iloc[i-1]['high'] and recent_df.iloc[i]['high'] > recent_df.iloc[i+1]['high']:
            peaks.append(recent_df.iloc[i]['high'])
        if recent_df.iloc[i]['low'] < recent_df.iloc[i-1]['low'] and recent_df.iloc[i]['low'] < recent_df.iloc[i+1]['low']:
            troughs.append(recent_df.iloc[i]['low'])

    lowest_low = min(troughs) if troughs else c['low']
    highest_high = max(peaks) if peaks else c['high']

    if c['close'] > c['open'] and p['open'] > p['close'] and c['close'] > p['open'] and c['open'] < p['close']:
        return "Bullish Engulfing", "Buy", min(c['low'], p['low']) * 0.998
    if c['close'] < c['open'] and p['close'] > p['open'] and c['close'] < p['open'] and c['open'] > p['close']:
        return "Bearish Engulfing", "Sell", max(c['high'], p['high']) * 1.002
    if lower_wick > (body * 2.5) and upper_wick < (body * 0.5):
        return "Hammer (Bullish Reversal)", "Buy", c['low'] * 0.998
    if upper_wick > (body * 2.5) and lower_wick < (body * 0.5):
        return "Shooting Star (Bearish)", "Sell", c['high'] * 1.002

    if len(troughs) >= 2:
        if abs(c['low'] - troughs[-1]) / troughs[-1] < 0.0015 and c['close'] > c['open']:
            return "Double Bottom", "Buy", lowest_low * 0.997
        if c['low'] < troughs[-1] and c['close'] > troughs[-1] and lower_wick > body:
            return "Swing Failure Pattern (SFP) Bottom", "Buy", c['low'] * 0.998
            
    if len(peaks) >= 2:
        if abs(c['high'] - peaks[-1]) / peaks[-1] < 0.0015 and c['close'] < c['open']:
            return "Double Top", "Sell", highest_high * 1.003
        if c['high'] > peaks[-1] and c['close'] < peaks[-1] and upper_wick > body:
            return "Swing Failure Pattern (SFP) Top", "Sell", c['high'] * 1.002

    if len(df) > 30:
        past_move = (df.iloc[-5]['close'] - df.iloc[-25]['close']) / df.iloc[-25]['close']
        consolidation_low = min(df.iloc[-5:]['low'])
        consolidation_high = max(df.iloc[-5:]['high'])
        if past_move > 0.05 and c['close'] > max(df.iloc[-5:-1]['high']):
            return "Bullish Flag Breakout", "Buy", consolidation_low * 0.998
        if past_move < -0.05 and c['close'] < min(df.iloc[-5:-1]['low']):
            return "Bearish Flag Breakdown", "Sell", consolidation_high * 1.002

    return "No Clear Pattern", "Neutral", None

def check_tp_sl():
    print("[THREAD] TP/SL Monitoring Thread Started.", flush=True)
    while True:
        try:
            all_futures = scan_all_binance_futures()
            if not all_futures: 
                time.sleep(5)
                continue
            prices = {coin['symbol']: float(coin['lastPrice']) for coin in all_futures}
            for base, trade in list(ACTIVE_TRADES.items()):
                symbol = base + "USDT"
                if symbol not in prices: continue
                
                curr = prices[symbol]
                tf = trade['tf']
                is_long = "LONG" in trade['dir']
                
                hit_tp = (is_long and curr >= trade['tp']) or (not is_long and curr <= trade['tp'])
                hit_sl = (is_long and curr <= trade['sl']) or (not is_long and curr >= trade['sl'])
                
                if hit_tp or hit_sl:
                    pnl = trade['tp_pct'] if hit_tp else -trade['sl_pct']
                    tp_inc = 1 if hit_tp else 0
                    sl_inc = 0 if hit_tp else 1
                    
                    for period in ["today", "weekly", "monthly"]:
                        STATS_DB[tf][period]["signals"] += 1
                        STATS_DB[tf][period]["tp_hit"] += tp_inc
                        STATS_DB[tf][period]["sl_hit"] += sl_inc
                        STATS_DB[tf][period]["pnl"] += pnl
                        
                    del ACTIVE_TRADES[base]
                    status = "🏆 TARGET HIT" if hit_tp else "📉 STOP LOSS HIT"
                    
                    msg = f"🔰 **${base}/USDT ({tf})** 🔰\n\nResult: {status}\nLeverage: {LEVERAGE}x ⚡\nPnL: {pnl:+.2f}%\nExit Price: {curr:.4f}"
                    bot.send_message(CHAT_ID, msg, parse_mode='Markdown')
        except Exception as e:
            print(f"[ERROR in check_tp_sl]: {e}", flush=True)
        time.sleep(5)

def auto_signal_generator_loop():
    print("[THREAD] Market Scanner Thread Started.", flush=True)
    while True:
        try:
            print(f"[SCANNER] Scanning started at {datetime.datetime.now().strftime('%H:%M:%S')}...", flush=True)
            all_coins = scan_all_binance_futures()
            if not all_coins:
                print("[SCANNER] No coin data received from Binance.", flush=True)
                time.sleep(SCAN_INTERVAL_SECONDS)
                continue
                
            coins = filter_scalping_coins(all_coins)
            print(f"[SCANNER] Top candidate coins for scanning: {[c['symbol'] for c in coins]}", flush=True)
            
            for coin in coins[:3]:
                symbol = coin['symbol']
                base = symbol.replace("USDT", "")
                if base in ACTIVE_TRADES: continue
                
                timeframe = random.choice(["1m", "5m"])
                df = get_klines_dataframe(symbol, timeframe, limit=500)
                if df is None or len(df) < 100: continue
                
                df = calculate_indicators(df)
                c_candle = df.iloc[-2]
                current_price = c_candle['close']
                
                pattern_name, action, pattern_sl = detect_chart_patterns(df)
                
                if action == "Neutral" or pattern_sl is None: 
                    continue
                
                print(f"[MATCH FOUND] {symbol} ({timeframe}) matched Pattern: {pattern_name} | Action: {action}", flush=True)
                
                # --- শুধুমাত্র আপনার দেওয়া ভলিউম SMA ১৪ ক্রসের কন্ডিশন রাখা হলো ---
                if c_candle['volume'] <= c_candle['Vol_SMA']: 
                    print(f"[FILTER SKIPPED] {symbol} Volume ({c_candle['volume']}) is NOT above Vol_SMA 14 ({c_candle['Vol_SMA']}).", flush=True)
                    continue
                
                # প্রাইস MA এবং ক্যান্ডেলস্টিক পজিশনের অন্য সব শর্ত সম্পূর্ণ বাদ দেওয়া হয়েছে।
                
                is_long = action == "Buy"
                trade_dir_text = "BUY (LONG) 🟢" if is_long else "SELL (SHORT) 🔴"
                
                sl = pattern_sl
                sl_dist = abs(current_price - sl)
                
                tp_dist = sl_dist * RISK_REWARD_RATIO
                tp = current_price + tp_dist if is_long else current_price - tp_dist
                
                sl_pct = (sl_dist / current_price) * 100 * LEVERAGE
                tp_pct = (tp_dist / current_price) * 100 * LEVERAGE
                
                if sl_pct > 150: 
                    print(f"[FILTER SKIPPED] {symbol} Stop Loss too wide ({sl_pct:.2f}%).", flush=True)
                    continue 

                signal_msg = (f"🎯 **AI Advanced Price Action Signal** 🔥\n\n"
                              f"Coin: ${base}/USDT\n"
                              f"Pattern: {pattern_name} 📊\n"
                              f"Timeframe: {timeframe} ⚡\n"
                              f"Direction: {trade_dir_text}\n"
                              f"Leverage: {LEVERAGE}x 🚀\n"
                              f"Entry: {current_price:.4f}\n"
                              f"TP: {tp:.4f} ({tp_pct:+.2f}%)\n"
                              f"SL: {sl:.4f} (-{sl_pct:.2f}%)\n"
                              f"Risk Reward: 1:{RISK_REWARD_RATIO}\n"
                              f"Time: {datetime.datetime.now().strftime('%H:%M:%S')}")
                              
                bot.send_message(CHAT_ID, signal_msg, parse_mode='Markdown')
                print(f"[SUCCESS] Signal sent for {symbol} to channel!", flush=True)
                
                ACTIVE_TRADES[base] = {
                    "dir": "LONG" if is_long else "SHORT", 
                    "entry": current_price, "tp": tp, "sl": sl,
                    "tp_pct": tp_pct, "sl_pct": sl_pct, "tf": timeframe
                }
                break
        except Exception as e:
            print(f"[ERROR in auto_signal_generator_loop]: {e}", flush=True)
        time.sleep(SCAN_INTERVAL_SECONDS)

def daily_auto_report_loop():
    while True:
        try:
            now = datetime.datetime.now()
            if now.hour == 0 and now.minute == 0:
                report_text = "📢 **Daily Automated Performance Report** 📢\n\n"
                for tf in ["1m", "5m"]:
                    data = STATS_DB[tf]["today"]
                    total = data["signals"]
                    tp = data["tp_hit"]
                    sl = data["sl_hit"]
                    pnl = data["pnl"]
                    acc = (tp / total * 100) if total > 0 else 0.0
                    
                    report_text += (f"⚡ **Timeframe: {tf}**\n"
                                    f"• Total Signals: {total}\n"
                                    f"• Total TP Hit: {tp} 🏆\n"
                                    f"• Total SL Hit: {sl} 📉\n"
                                    f"• Accuracy Rate: {acc:.1f}%\n"
                                    f"• Total Profit/Loss: {pnl:+.2f}% (50x)\n\n")
                
                bot.send_message(CHAT_ID, report_text, parse_mode='Markdown')
                STATS_DB["1m"]["today"] = {"signals": 0, "tp_hit": 0, "sl_hit": 0, "pnl": 0.0}
                STATS_DB["5m"]["today"] = {"signals": 0, "tp_hit": 0, "sl_hit": 0, "pnl": 0.0}
                time.sleep(60)
        except Exception as e:
            print(f"[ERROR in daily_auto_report_loop]: {e}", flush=True)
        time.sleep(30)

@bot.message_handler(commands=['start', 'status'])
def start(msg):
    bot.send_message(msg.chat.id, f"🤖 **বট স্ট্যাটাস:** অ্যাক্টিভ 🟢\n📊 **অ্যানালাইসিস:** 1m এবং 5m স্ক্যানিং সচল\n🚀 **লেভারেজ হিসাব:** {LEVERAGE}x\n⚙️ **রিস্ক লজিক:** Pattern-wise SL + 1:{RISK_REWARD_RATIO} TP")

def generate_report_text(tf):
    data = STATS_DB[tf]
    text = f"📊 **{tf} Performance Report (50x Leverage)** 📊\n\n"
    for period in ["today", "weekly", "monthly"]:
        total = data[period]["signals"]
        tp = data[period]["tp_hit"]
        sl = data[period]["sl_hit"]
        pnl = data[period]["pnl"]
        acc = (tp / total * 100) if total > 0 else 0.0
        
        text += (f"🔹 **{period.capitalize()} Performance:**\n"
                 f"   • Total Signals: {total}\n"
                 f"   • Total TP Hit: {tp}\n"
                 f"   • Total SL Hit: {sl}\n"
                 f"   • Win Accuracy: {acc:.1f}%\n"
                 f"   • Total Profit/Loss: {pnl:+.2f}%\n\n")
    return text

@bot.message_handler(commands=['report_1m'])
def report_1m(msg):
    bot.send_message(msg.chat.id, generate_report_text("1m"), parse_mode='Markdown')

@bot.message_handler(commands=['report_5m'])
def report_5m(msg):
    bot.send_message(msg.chat.id, generate_report_text("5m"), parse_mode='Markdown')

@bot.message_handler(commands=['signals'])
def active_signals(msg):
    if not ACTIVE_TRADES:
        bot.send_message(msg.chat.id, "❌ কোনো সিগনাল চলমান নেই।")
        return
    text = "⏳ **চলমান সিগনালসমূহ:**\n\n"
    for coin, details in ACTIVE_TRADES.items():
        text += f"• **{coin}** ({details['tf']}) -> {details['dir']}\n"
    bot.send_message(msg.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['close'])
def manual_close(msg):
    try:
        coin_to_close = msg.text.split()[1].upper().replace("USDT", "")
        if coin_to_close in ACTIVE_TRADES:
            del ACTIVE_TRADES[coin_to_close]
            bot.send_message(msg.chat.id, f"✅ {coin_to_close}/USDT ক্লোজ করা হয়েছে।")
        else:
            bot.send_message(msg.chat.id, f"❌ {coin_to_close} খুঁজে পাওয়া যায়নি।")
    except:
        bot.send_message(msg.chat.id, "⚠️ नियम: `/close SOL`", parse_mode='Markdown')

if __name__ == '__main__':
    print("[START] Initializing Bot Script...", flush=True)
    load_pdf_from_telegram_channel()
    set_bot_commands()
    
    Thread(target=auto_signal_generator_loop, daemon=True).start()
    Thread(target=check_tp_sl, daemon=True).start()
    Thread(target=daily_auto_report_loop, daemon=True).start()
    
    print("[START] Telegram Polling Started. Bot is live!", flush=True)
    bot.infinity_polling(none_stop=True)
