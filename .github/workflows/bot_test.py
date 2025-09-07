import yfinance as yf
import requests

# --- CONFIGURACIÓN ---
TOKEN = "8302867942:AAGh4S9byssyx_4FhCzPSVpdxjSo9AlS4Q4"  # Token del bot
CHAT_ID = "7719744456"  # Tu chat ID

# --- DESCARGAR DATOS DE UNA ACCIÓN ---
ticker = "AAPL"
data = yf.download(ticker, period="1d", interval="1m")

# Obtener último dato
last_row = data.tail(1)
precio = last_row['Close'].values[0]

# --- ENVIAR A TELEGRAM ---
mensaje = f"📈 Reporte de {ticker}\nPrecio actual: {precio:.2f} USD"

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = {"chat_id": CHAT_ID, "text": mensaje}
requests.post(url, data=payload)

print("Mensaje enviado a Telegram:", mensaje)
