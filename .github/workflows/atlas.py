import requests
import json
import os
from datetime import datetime

# === CONFIGURACIÓN ===
TELEGRAM_BOT_TOKEN = "TU_TOKEN_AQUI"
TELEGRAM_CHAT_ID = "TU_CHAT_ID_AQUI"
API_KEY = "demo"  # Reemplázalo con tu API Key real si usas Alpha Vantage u otro servicio
FX_RATE = 18.5  # Tipo de cambio MXN/USD

# === CARGAR PORTAFOLIO ===
with open("portfolio.json", "r") as f:
    portfolio = json.load(f)

# === FUNCIONES ===

def send_telegram_message(message):
    """Enviar mensaje a Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, json=payload)

def get_stock_price(symbol):
    """Obtener precio actual de la acción"""
    try:
        url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={API_KEY}"
        response = requests.get(url)
        data = response.json()
        price = float(data["Global Quote"]["05. price"])
        return price
    except:
        return None

def check_signals(symbol, shares, buy_price):
    """Analizar acción según reglas"""
    current_price = get_stock_price(symbol)
    if current_price is None:
        return f"Error obteniendo precio de {symbol}"

    # Calcular ganancia/pérdida
    total_investment = shares * buy_price
    current_value = shares * current_price
    pl_usd = current_value - total_investment
    pl_mxn = pl_usd * FX_RATE

    # Señales según tu estrategia
    if current_price >= 53.50 and current_price < 55.00:
        signal = "TAKE-PROFIT: Vender 50% de la posición."
    elif current_price >= 55.00:
        signal = "MOMENTUM: Vender 50% o aplicar trailing stop."
    elif current_price <= 49.00:
        signal = "PROTECT CAPITAL: Vender TODAS las acciones."
    else:
        signal = "HOLD: Mantener posición."

    message = (
        f"\n📊 {symbol}\n"
        f"Precio actual: ${current_price:.2f} USD\n"
        f"Ganancia/Pérdida: ${pl_usd:.2f} USD | ${pl_mxn:.2f} MXN\n"
        f"Acciones: {shares}\n"
        f"Señal: {signal}\n"
        f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram_message(message)
    return message

# === EJECUCIÓN ===
for symbol, data in portfolio.items():
    result = check_signals(symbol, data["shares"], data["buy_price"])
    print(result)
