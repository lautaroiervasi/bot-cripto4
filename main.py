import time
import logging
import pandas as pd
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException
import telegram
import ta
import asyncio
import nest_asyncio
import os

nest_asyncio.apply()

# ===== CONFIG =====
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

BASE_URL = 'https://testnet.binance.vision'
MODO_PRUEBA = True

# ===== LOGGING =====
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# ===== INICIALIZAR CLIENTES =====
client = Client(API_KEY, API_SECRET, testnet=True)
client.API_URL = BASE_URL
bot_telegram = telegram.Bot(token=TELEGRAM_TOKEN)

def send_telegram_message(text):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(bot_telegram.send_message(chat_id=TELEGRAM_CHAT_ID, text=text))
        else:
            loop.run_until_complete(bot_telegram.send_message(chat_id=TELEGRAM_CHAT_ID, text=text))
    except Exception as e:
        logging.error(f"Error enviando Telegram: {e}")

def obtener_historico(symbol, interval='1h', lookback=200):
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=lookback)
        df = pd.DataFrame(klines, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df = df.astype({
            'open': 'float', 'high': 'float', 'low': 'float',
            'close': 'float', 'volume': 'float'
        })
        return df
    except Exception as e:
        logging.error(f"Error obteniendo histórico: {e}")
        return None

def calcular_indicadores(df):
    df['ema9'] = ta.trend.ema_indicator(df['close'], window=9)
    df['ema21'] = ta.trend.ema_indicator(df['close'], window=21)
    df['rsi'] = ta.momentum.rsi(df['close'], window=14)
    macd = ta.trend.MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['vol_sma20'] = df['volume'].rolling(window=20).mean()
    df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
    return df

def evaluar_senal(df):
    if len(df) < 2:
        return False
    if (
        df['ema9'].iloc[-2] < df['ema21'].iloc[-2] and df['ema9'].iloc[-1] > df['ema21'].iloc[-1] and
        df['rsi'].iloc[-1] < 70 and
        df['macd'].iloc[-1] > df['macd_signal'].iloc[-1] and
        df['volume'].iloc[-1] > df['vol_sma20'].iloc[-1]
    ):
        return True
    return False

def obtener_balance(symbol):
    try:
        asset = symbol.replace('USDT','')
        balance = client.get_asset_balance(asset)
        return float(balance['free']) if balance else 0.0
    except Exception as e:
        logging.error(f"Error obteniendo balance: {e}")
        return 0.0

def ejecutar_compra(symbol, usdt_amount):
    if MODO_PRUEBA:
        logging.info(f"[MODO PRUEBA] Simulando compra de {symbol} por {usdt_amount} USDT")
        send_telegram_message(f"[PRUEBA] Señal de compra para {symbol} por {usdt_amount} USDT (simulado).")
        return None
    try:
        price = float(client.get_symbol_ticker(symbol=symbol)['price'])
        quantity = round(usdt_amount / price, 5)
        order = client.order_market_buy(symbol=symbol, quantity=quantity)
        send_telegram_message(f"✅ Comprado {quantity} {symbol} a precio {price}")
        return order
    except BinanceAPIException as e:
        logging.error(f"Error ejecutando compra: {e}")
        send_telegram_message(f"❌ Error compra {symbol}: {e}")
        return None

def main_loop():
    simbolos = ['BTCUSDT', 'ETHUSDT', 'DOGEUSDT']
    saldo_usdt = 10
    while True:
        for symbol in simbolos:
            logging.info(f"Analizando {symbol}")
            df = obtener_historico(symbol)
            if df is None or df.empty:
                continue
            df = calcular_indicadores(df)
            if evaluar_senal(df):
                balance = obtener_balance(symbol)
                if balance < 1:
                    ejecutar_compra(symbol, saldo_usdt)
                else:
                    logging.info(f"No se compra {symbol}, ya hay balance")
            else:
                logging.info(f"No hay señal para {symbol}")
            time.sleep(3)
        logging.info("Esperando 5 minutos para próximo análisis...")
        time.sleep(300)

if __name__ == "__main__":
    send_telegram_message("🤖 Bot iniciado en modo prueba (Render).")
    try:
        main_loop()
    except KeyboardInterrupt:
        logging.info("Bot detenido manualmente.")
        send_telegram_message("🛑 Bot detenido manualmente.")
    except Exception as e:
        logging.error(f"Error inesperado: {e}")
        send_telegram_message(f"❌ Error inesperado: {e}")
