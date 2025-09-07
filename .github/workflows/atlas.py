import os
import json
import yfinance as yf
import requests
from datetime import datetime

# Cargar configuración
BOT_TOKEN = os.getenv("8181571309:AAHAZxlYcKlx7ZmIvH1JGLRVTKT5l3dp_kU")
CHAT_ID = os.getenv("7719744456")

# Leer portafolio
with open("portfolio.json", "r") as f:
    portfolio = json.load(f)

# Obtener tipo de cambio USD/MXN
def get_usd_mxn():
    url = "https://api.exchangerate-api.com/v4/latest/USD"
    response = requests.get(url).json()
    return response['rates']['MXN']

# Enviar mensaje a Telegram
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": 7719744456, "text": msg, "parse_mode": "Markdown"}
    requests.post(url, data=data)

# Analizar una acción
def analyze_stock(ticker, shares, buy_price):
    data = yf.download(ticker, period="1d", interval="1m")
    if data.empty:
        return None

    last_price = data['Close'].iloc[-1]
    avg_volume = data['Volume'].tail(20).mean()
    today_volume = data['Volume'].iloc[-1]
    fx = get_usd_mxn()

    pnl_usd = (last_price - buy_price) * shares
    pnl_mxn = pnl_usd * fx

    action = "HOLD"
    reason = "Ninguna condición cumplida."

    # Reglas
    if last_price >= 53.50:
        action = "SELL 50%"
        reason = "Tomar ganancias parciales."
    elif last_price >= 55.00 and today_volume >= 1.5 * avg_volume:
        action = "SELL TRAIL"
        reason = "Venta por momentum y alto volumen."
    elif last_price <= 49.00:
        action = "SELL ALL"
        reason = "Proteger capital por caída."

    message = (
        f"📊 *REPORTE {ticker}*\n"
        f"Fecha/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Precio Actual: {last_price:.2f} USD\n"
        f"P/L: {pnl_usd:.2f} USD | {pnl_mxn:.2f} MXN\n"
        f"Volumen Hoy: {today_volume}\n"
        f"Volumen Prom 20d: {avg_volume:.0f}\n\n"
        f"✅ *ACCIÓN:* {action}\n"
        f"Razón: {reason}"
    )

    send_telegram(message)
    print(message)

# Revisar todas las acciones del portafolio
for ticker, info in portfolio.items():
    analyze_stock(ticker, info['shares'], info['buy_price'])
