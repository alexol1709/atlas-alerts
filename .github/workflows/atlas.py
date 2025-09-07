print(" Iniciando atlas.py...")
import requests
import yfinance as yf
import json
from datetime import datetime

# ===========================
# CONFIGURACIÓN
# ===========================
TELEGRAM_BOT_TOKEN = "8302867942:AAGh4S9byssyx_4FhCzPSVpdxjSo9AlS4Q4"
TELEGRAM_CHAT_ID = "7719744456"
FX_RATE = 18.5  # Tipo de cambio MXN/USD

# ===========================
# FUNCIÓN PARA ENVIAR MENSAJES
# ===========================
def send_telegram_message(message):
    """
    Envía un mensaje al bot de Telegram
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    response = requests.post(url, data=payload)
    return response.json()

# ===========================
# OBTENER DATOS DE UNA ACCIÓN
# ===========================
def get_stock_data(ticker):
    """
    Obtiene datos de la acción desde Yahoo Finance
    """
    data = yf.download(ticker, period="1d", interval="1m")
    data = yf.download("CYTK", period="1d", interval="1m")

if data.empty:
    print("⚠️ No se pudo obtener datos para CYTK")
else:
    last_price = data["Close"].iloc[-1]
    print(f"Último precio CYTK: {last_price}")

# ===========================
# LÓGICA DE ANÁLISIS
# ===========================
def analyze_and_alert(ticker, shares, cost):
    result = get_stock_data(ticker)
    if not result:
        send_telegram_message(f"❌ Error obteniendo precio de {ticker}")
        return

    last_price, vol_today, vol_avg20 = result

    # Cálculo P/L
    pnl_usd = (last_price - cost) * shares
    pnl_mxn = pnl_usd * FX_RATE

    # Decisión básica
    if last_price < cost * 0.9:
        action = "SELL"
        reason = "Precio cayó más de 10%"
    elif last_price > cost * 1.1:
        action = "SELL"
        reason = "Precio subió más de 10% (tomar ganancias)"
    else:
        action = "HOLD"
        reason = "Dentro de rango normal"

    # Mensaje final
    message = (
        f"📊 REPORTE {ticker}\n"
        f"Fecha/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Precio Actual: {last_price:.2f} USD\n"
        f"P/L: {pnl_usd:.2f} USD | {pnl_mxn:.2f} MXN\n"
        f"Volumen Hoy: {vol_today:,}\n"
        f"Volumen Prom 20d: {vol_avg20:,}\n\n"
        f"✅ ACCIÓN: {action}\n"
        f"Razón: {reason}"
    )

    # Enviar reporte a Telegram
    send_telegram_message(message)

# ===========================
# EJECUCIÓN
# ===========================
if __name__ == "__main__":
    # Aquí defines tus parámetros
    ticker = "CYTK"      # Cambia el ticker según la acción
    shares = 10           # Número de acciones que tienes
    cost = 52.00          # Precio de compra por acción en USD

    analyze_and_alert(ticker, shares, cost)
