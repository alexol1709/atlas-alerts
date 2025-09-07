# atlas.py
import os
import json
import time
from datetime import datetime, timezone

import requests
import pandas as pd
import yfinance as yf

# =========================
# CONFIG (defaults seguros)
# =========================
# Tu posición base (puedes cambiarlo o moverlo a portfolio.json si quieres)
CYTK_SHARES = 21
CYTK_COST = 50.99

# Triggers
TAKE_PROFIT = 53.50   # A) vender parcial
MOMO_PRICE   = 55.00  # B) vender 50% o trail
MOMO_VOL_X   = 1.5    # vol >= 150% de la media 20d
STOP_ALL     = 49.00  # C) vender todo

# Telegram
BOT_TOKEN = os.getenv("8302867942:AAGh4S9byssyx_4FhCzPSVpdxjSo9AlS4Q4", "").strip()
CHAT_ID   = os.getenv("7719744456", "").strip()

# atlas.py — robusto para fuera de horario / fines de semana

import os, json, math, time, datetime as dt
import requests
import yfinance as yf

# ============ CONFIG ============
TELEGRAM_BOT_TOKEN = os.getenv("8302867942:AAGh4S9byssyx_4FhCzPSVpdxjSo9AlS4Q4")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "7719744456")
USD_MXN            = float(os.getenv("FX_RATE", "18.5"))  # usa valor aproximado si no hay FX live
TICKER             = "CYTK"                               # único por ahora

# Reglas del usuario:
TAKE_PROFIT_A = 53.50
MOMO_PRICE_B  = 55.00
MOMO_VOL_X    = 1.5     # 150% del promedio 20d
STOP_C        = 49.00

# ============ UTIL ============

def send_telegram(msg: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()

def robust_last_price_and_volume(ticker: str):
    """
    1) intenta 1m/5m intradía con prepost
    2) si falla, usa 1h o diario
    Devuelve: price (float), vol_hoy (int), vol_avg20 (float)
    """
    # intentos por orden
    tries = [
        dict(interval="1m", period="1d"),
        dict(interval="5m", period="5d"),
        dict(interval="1h", period="5d"),
        dict(interval="1d", period="3mo"),
    ]
    last_price = None
    vol_today  = None
    vol_avg20  = None

    # volumen promedio 20d (diario)
    try:
        ddf = yf.download(ticker, interval="1d", period="6mo", prepost=True, progress=False)
        if not ddf.empty:
            vol_avg20 = float(ddf["Volume"].tail(20).mean())
    except Exception:
        vol_avg20 = None

    for cfg in tries:
        try:
            df = yf.download(ticker, prepost=True, progress=False, **cfg)
            if df is None or df.empty:
                continue
            # precio
            last_price = float(df["Close"].dropna().iloc[-1])
            # volumen de hoy: si la descarga fue intradía, suma; si fue diario, usa el último
            if cfg["interval"] in ("1m","5m","1h"):
                same_day = df.index.tz_convert("America/New_York") if hasattr(df.index, "tz_convert") else df.index
                if hasattr(same_day, "date"):
                    # agrupa por día
                    vol_today = int(df["Volume"].fillna(0).tail(390).sum())
                else:
                    vol_today = int(df["Volume"].fillna(0).sum())
            else:
                vol_today = int(df["Volume"].dropna().iloc[-1])
            # si aún no tenemos vol_avg20, intenta calcular con df diario
            if vol_avg20 is None and cfg["interval"] == "1d":
                vol_avg20 = float(df["Volume"].tail(20).mean())
            break
        except Exception:
            continue

    return last_price, vol_today, vol_avg20

def compute_pl(shares, cost, price):
    pnl_usd = (price - cost) * shares
    pnl_mxn = pnl_usd * USD_MXN
    return pnl_usd, pnl_mxn

# ============ LÓGICA ============

def decide_action(price, vol_today, vol_avg20, negative_news=False):
    """
    Devuelve (action, reason)
    """
    # Regla C: proteger capital por precio o noticia negativa
    if price is not None and price <= STOP_C:
        return "SELL ALL", f"Precio <= {STOP_C:.2f}"
    if negative_news:
        return "SELL ALL", "Noticia negativa"

    # Regla A: toma parcial
    if price is not None and price >= TAKE_PROFIT_A:
        return "TAKE-PROFIT PARTIAL", f"Precio >= {TAKE_PROFIT_A:.2f}"

    # Regla B: momentum + volumen
    if price is not None and vol_today and vol_avg20:
        if price >= MOMO_PRICE_B and vol_today >= MOMO_VOL_X * vol_avg20:
            return "MOMENTUM: SELL 50% / TRAIL", f"Precio >= {MOMO_PRICE_B:.2f} y Vol >= {MOMO_VOL_X:.1f}× promedio"

    # Si nada se cumple
    return "HOLD", "Ninguna condición activa"

def main():
    # leer portfolio.json
    with open("portfolio.json","r") as f:
        portfolio = json.load(f)
    pos = portfolio.get(TICKER)
    if not pos:
        send_telegram(f"❗No encontré {TICKER} en portfolio.json")
        return

    shares = int(pos["shares"])
    cost   = float(pos["buy_price"])

    price, vol_today, vol_avg20 = robust_last_price_and_volume(TICKER)
    if price is None:
        send_telegram("⚠️ No pude obtener precio de CYTK (fuera de horario/limite de datos). Intenta más tarde.")
        return

    pnl_usd, pnl_mxn = compute_pl(shares, cost, price)
    # (placeholder) noticias negativas detectadas por otra parte del flujo
    negative = False

    action, reason = decide_action(price, vol_today, vol_avg20, negative_news=negative)

    ts = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    msg = (
        f"<b>📊 REPORTE {TICKER}</b>\n"
        f"<b>Fecha/Hora:</b> {ts}\n"
        f"<b>Precio:</b> ${price:.2f} USD\n"
        f"<b>Vol hoy:</b> {vol_today if vol_today is not None else 'N/D'}\n"
        f"<b>Vol 20d:</b> {int(vol_avg20) if vol_avg20 else 'N/D'}\n"
        f"<b>P/L:</b> ${pnl_usd:.2f} USD | ${pnl_mxn:.2f} MXN (fx≈{USD_MXN})\n\n"
        f"<b>✅ ACCIÓN:</b> {action}\n"
        f"<i>Razón:</i> {reason}\n"
        f"Reglas: A){TAKE_PROFIT_A:.2f} | B){MOMO_PRICE_B:.2f}+Vol≥{MOMO_VOL_X:.1f}× | C){STOP_C:.2f} o noticia negativa"
    )
    send_telegram(msg)

if __name__ == "__main__":
    main()
