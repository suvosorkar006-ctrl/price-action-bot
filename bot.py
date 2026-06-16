import os
import requests
import datetime
import pypdf
import random
import logging
import time
from threading import Thread
from telebot import TeleBot, types

logging.getLogger("pypdf").setLevel(logging.ERROR)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or "8834283543:AAH26mFLUbr8PaFEFglqgERnvM1ArKlnhPU"
CHAT_ID = os.getenv("CHAT_ID") or "-1004453763468"
SCAN_INTERVAL_SECONDS = 30

bot = TeleBot(TELEGRAM_TOKEN)
PDF_DATABASE = ""
ACTIVE_TRADES = {}

STATS_DB = {
    "1m": {
        "today": {"signals": 0, "wins": 0, "pnl": 0.0},
        "weekly": {"signals": 0, "wins": 0, "pnl": 0.0},
        "monthly": {"signals": 0, "wins": 0, "pnl": 0.0},
    },
    "5m": {
        "today": {"signals": 0, "wins": 0, "pnl": 0.0},
        "weekly": {"signals": 0, "wins": 0, "pnl": 0.0},
        "monthly": {"signals": 0, "wins": 0, "pnl": 0.0},
    }
}

def set_bot_commands():
    try:
        commands = [
            types.BotCommand("start", "বট মেইন মেনু"),
            types.BotCommand("report_1m", "১ মিনিটের সিগনাল রিপোর্ট"),
            types.BotCommand("report_5m", "৫ মিনিটের সিগনাল রিপোর্ট"),
            types.BotCommand("signals", "বর্তমানে চলমান লাইভ সিগনাল"),
            types.BotCommand("status", "বটের বর্তমান স্ট্যাটাস"),
            types.BotCommand("close", "ম্যানুয়াল ক্লোজ (উদা: /close SOL)")
        ]
        bot.set_my_commands(commands)
    except:
        pass

def load_pdf_from_telegram_channel():
    global PDF_DATABASE
    PDF_DATABASE = "order block liquidity sweep breakout fvg bullish flag scalping 1m 5m"

def scan_all_binance_futures():
    try:
        res = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=10).json()
        return [t for t in res if t['symbol'].endswith('USDT')]
    except:
        return []

def filter_scalping_coins(all_coins):
    valid = []
    random.shuffle(all_coins)
    for coin in all_coins:
        if abs(float(coin.get('priceChangePercent', 0))) >= 0.8 and float(coin.get('volume', 0)) > 200000:
            valid.append(coin)
            if len(valid) >= 5:
                break
    return valid

def check_tp_sl():
    while True:
        try:
            prices = {coin['symbol']: float(coin['lastPrice']) for coin in scan_all_binance_futures()}
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
                    win = 1 if hit_tp else 0
                    
                    for period in ["today", "weekly", "monthly"]:
                        STATS_DB[tf][period]["signals"] += 1
                        STATS_DB[tf][period]["wins"] += win
                        STATS_DB[tf][period]["pnl"] += pnl
                        
                    del ACTIVE_TRADES[base]
                    status = "🏆 TARGET HIT" if hit_tp else "📉 STOP LOSS HIT"
                    
                    msg = f"🔰 **${base}/USDT ({tf})** 🔰\n\nResult: {status}\nPnL: {pnl:+.2f}%\nExit Price: {curr:.4f}"
                    bot.send_message(CHAT_ID, msg, parse_mode='Markdown')
        except:
            pass
        time.sleep(5)

def auto_signal_generator_loop():
    while True:
        try:
            coins = filter_scalping_coins(scan_all_binance_futures())
            for coin in coins[:2]:
                base = coin['symbol'].replace("USDT", "")
                if base in ACTIVE_TRADES: continue
                
                price = float(coin['lastPrice'])
                is_long = float(coin['priceChangePercent']) > 0
                direction = "BUY (LONG)" if is_long else "SELL (SHORT)"
                timeframe = random.choice(["1m", "5m"])
                
                vol = random.uniform(0.01, 0.02) if timeframe == "1m" else random.uniform(0.02, 0.04)
                rr = random.uniform(2.0, 3.5)
                
                sl = price * (1 - vol) if is_long else price * (1 + vol)
                tp = price * (1 + vol * rr) if is_long else price * (1 - vol * rr)
                
                signal = f"🎯 **Price Action Scalping Signal** 🔥\n\nCoin: ${base}/USDT\nTimeframe: {timeframe} ⚡\nDirection: {direction}\nEntry: {price:.4f}\nTP: {tp:.4f}\nSL: {sl:.4f}\nRisk Reward: 1:{rr:.2f}\nTime: {datetime.datetime.now().strftime('%H:%M:%S')}"
                bot.send_message(CHAT_ID, signal, parse_mode='Markdown')
                
                ACTIVE_TRADES[base] = {
                    "dir": direction, "entry": price, "tp": tp, "sl": sl,
                    "tp_pct": vol * rr * 100, "sl_pct": vol * 100, "tf": timeframe
                }
        except:
            pass
        time.sleep(SCAN_INTERVAL_SECONDS)

@bot.message_handler(commands=['start', 'status'])
def start(msg):
    bot.send_message(msg.chat.id, "🤖 **বট স্ট্যাটাস:** অ্যাক্টিভ\n⏰ **টাইমিং:** ২৪ ঘণ্টা\n📊 **স্ক্যান:** ৩০ সেকেন্ড\n⚡ **টাইমফ্রেম:** 1m এবং 5m স্ক্যাল্পিং রানিং।")

@bot.message_handler(commands=['report_1m'])
def report_1m(msg):
    data = STATS_DB["1m"]
    text = "📊 **1-Minute Report** 📊\n\n"
    for period in ["today", "weekly", "monthly"]:
        total = data[period]["signals"]
        wins = data[period]["wins"]
        acc = (wins / total * 100) if total > 0 else 0.0
        pnl = data[period]["pnl"]
        text += f"🔹 **{period.capitalize()}:**\n   • Signals: {total}\n   • Accuracy: {acc:.1f}%\n   • Profit: {pnl:+.2f}%\n\n"
    bot.send_message(msg.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['report_5m'])
def report_5m(msg):
    data = STATS_DB["5m"]
    text = "📊 **5-Minute Report** 📊\n\n"
    for period in ["today", "weekly", "monthly"]:
        total = data[period]["signals"]
        wins = data[period]["wins"]
        acc = (wins / total * 100) if total > 0 else 0.0
        pnl = data[period]["pnl"]
        text += f"🔹 **{period.capitalize()}:**\n   • Signals: {total}\n   • Accuracy: {acc:.1f}%\n   • Profit: {pnl:+.2f}%\n\n"
    bot.send_message(msg.chat.id, text, parse_mode='Markdown')

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
        bot.send_message(msg.chat.id, "⚠️ নিয়ম: `/close SOL`", parse_mode='Markdown')

if __name__ == '__main__':
    load_pdf_from_telegram_channel()
    set_bot_commands()
    Thread(target=auto_signal_generator_loop, daemon=True).start()
    Thread(target=check_tp_sl, daemon=True).start()
    bot.infinity_polling(none_stop=True)
