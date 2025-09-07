# -*- coding: utf-8 -*-
"""
ATLAS Alerts - Integración Alpha Vantage + Telegram

Este script:
- Lee tu portafolio desde portfolio.json
- Consulta el precio actual de cada acción vía Alpha Vantage
- Calcula ganancia/perdida en USD y MXN
- Evalúa reglas A, B, C
- Envía reporte detallado a tu bot de Telegram
"""

import os
import json
from datetime import datetime
import requests

# ========= CONFIG TELEGRAM =========
TELEGRAM_BOT_TOKEN = "8302867942:AAGh4S9byssyx_4FhCzPSVpdxjSo9AlS4Q4"  # Tu bot token
TELEGRAM_CHAT_ID = "7719744456"  # Tu chat ID

# ========= CONFIG ALPHA VANTAGE =========
# Se usa la clave desde variable de entorno para seguridad
ALPHAVANTAGE_KEY = os.environ.get("ALPHAVANTAGE_KEY")

# Archivo de portafolio
PORTFOLIO_FILE = "portfolio.json"

# Si el archivo no existe, usará estos símbolos como prueba
DEFAULT_SYMBOLS = ["CYTK"]

# ========= REGLAS DE ALERTA =========
RULE_A_TAKE_PROFIT = 53.50     # A) Tomar ganancia parcial si precio >= A
RULE_B_ADD_IF_DIP = 55.00      # B) Reforzar si precio < B
RULE_C_HARD_SELL = 49.00       # C) Venta fuerte si precio <= C

# ========= FUNCIONES AUXILIARES =========
def read_json(path: str) -> dict:
    """Lee un archivo JSON y regresa diccionario"""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def fmt_money(x: float) -> str:
    """Formatea valores monetarios"""
    try:
        return f"{x:,.2f}"
    except:
        return str(x)

def send_telegram(text: str) -> None:
    """Envía mensaje a Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print("Error enviando a Telegram:", e)

# ========= OBTENER DATOS DE ALPHA VANTAGE =========
def get_price_alpha(symbol: str) -> float:
    """Obtiene el precio actual de la acción desde Alpha Vantage"""
    if not ALPHAVANTAGE_KEY:
        raise ValueError("Falta la variable ALPHAVANTAGE_KEY. Exporta tu clave primero.")

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
        "apikey": ALPHAVANTAGE_KEY
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    if "Global Quote" not in data or "05. price" not in data["Global Quote"]:
        raise ValueError(f"Respuesta inválida de Alpha Vantage: {data}")

    return float(data["Global Quote"]["05. price"])

def get_usd_mxn_rate() -> float:
    """Obtiene el tipo de cambio USD/MXN"""
    # 1. Si está definido como variable de entorno
    fx = os.environ.get("FX_RATE")
    if fx:
        try:
            return float(fx)
        except:
            pass

    # 2. Consulta a Alpha Vantage
    if ALPHAVANTAGE_KEY:
        try:
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": "USD",
                "to_currency": "MXN",
                "apikey": ALPHAVANTAGE_KEY
            }
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            return float(data["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
        except:
            pass

    # 3. Valor fijo de respaldo
    return 18.5

# ========= LÓGICA DE ANÁLISIS =========
def analyze_symbol(symbol: str, shares: float, buy_price: float, fx_rate: float):
    """Analiza un símbolo y determina acción a tomar"""
    price = get_price_alpha(symbol)
    pnl_usd = (price - buy_price) * shares
    pnl_mxn = pnl_usd * fx_rate

    action = "HOLD"
    reason = "Sin condición activada."

    if price >= RULE_A_TAKE_PROFIT:
        action = "TAKE PROFIT"
        reason = f"Precio >= A ({RULE_A_TAKE_PROFIT})"
    if price <= RULE_C_HARD_SELL:
        action = "SELL"
        reason = f"Precio <= C ({RULE_C_HARD_SELL})"
    if price < RULE_B_ADD_IF_DIP and action != "SELL":
        reason += f" | Cerca de B ({RULE_B_ADD_IF_DIP})"

    return price, pnl_usd, pnl_mxn, action, reason

def build_report_line(symbol, price, pnl_usd, pnl_mxn, action, reason):
    return (
        f"*{symbol}*\n"
        f"Precio: {fmt_money(price)} USD\n"
        f"P/L: {fmt_money(pnl_usd)} USD | {fmt_money(pnl_mxn)} MXN\n"
        f"*ACCIÓN:* {action}\n"
        f"Razón: {reason}\n"
        "— — — — —\n"
    )

# ========= EJECUCIÓN PRINCIPAL =========
def run_once():
    fx_rate = get_usd_mxn_rate()
    portfolio = read_json(PORTFOLIO_FILE)
    lines = []

    if not portfolio:
        for sym in DEFAULT_SYMBOLS:
            price = get_price_alpha(sym)
            lines.append(
                f"*{sym}*\n"
                f"Precio: {fmt_money(price)} USD\n"
                f"(sin P/L definido)\n"
                "— — — — —\n"
            )
    else:
        for sym, pos in portfolio.items():
            shares = float(pos.get("shares", 0))
            buy_price = float(pos.get("buy_price", 0.0))
            price, pnl_usd, pnl_mxn, action, reason = analyze_symbol(sym, shares, buy_price, fx_rate)
            lines.append(build_report_line(sym, price, pnl_usd, pnl_mxn, action, reason))

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    header = (
        "📊 *REPORTE ATLAS*\n"
        f"Fecha/Hora: {timestamp}\n"
        f"FX (USD→MXN): {fmt_money(fx_rate)}\n"
        "— — — — —\n"
    )
    msg = header + "".join(lines)
    print(msg)
    send_telegram(msg)

# ========= MODO CHECK RÁPIDO =========
def quick_check(ticker: str):
    fx_rate = get_usd_mxn_rate()
    price = get_price_alpha(ticker)
    msg = (
        f"⚡ *CHECK RÁPIDO* {ticker}\n"
        f"Precio: {fmt_money(price)} USD\n"
        f"FX (USD→MXN): {fmt_money(fx_rate)}"
    )
    print(msg)
    send_telegram(msg)

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 2:
        quick_check(sys.argv[1].upper())
    else:
        run_once()
