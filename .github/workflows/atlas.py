# atlas.py
import os
import json
import time
from datetime import datetime, timezone

# --- PRECIOS / OHLC CON SESIÓN PROPIA ---
import requests, time
import yfinance as yf
import pandas as pd
import os, math, json, urllib.parse

def _alpha_json(function: str, params: dict) -> dict | None:
    key = os.environ.get("ALPHAVANTAGE_KEY")
    if not key: return None
    base = "https://www.alphavantage.co/query"
    q = {"function": function, "apikey": key, **params}
    url = f"{base}?{urllib.parse.urlencode(q)}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        if "Note" in data or "Information" in data:
            return None
        return data
    except Exception:
        return None

def get_last_price_fast(ticker: str) -> float | None:
    px = None
    # 1) Yahoo
    try:
        sess = _yf_session()
        q = yf.Ticker(ticker, session=sess).fast_info
        px = float(q.get("last_price") or q.get("lastPrice") or 0.0)
    except Exception:
        px = None
    # 2) Alpha Vantage si Yahoo falla
    if not px or px <= 0:
        px = get_last_price_av(ticker)
    return px if px and px > 0 else None
def _yf_session():
    s = requests.Session()
    # User-Agent “real” para que Yahoo no bloquee
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    })
    return s

def get_last_price_fast(ticker: str) -> float | None:
    """Intenta precio con yfinance; si falla, devuelve None."""
    try:
        sess = _yf_session()
        q = yf.Ticker(ticker, session=sess).fast_info
        px = float(q.get("last_price") or q.get("lastPrice") or 0.0)
        return px if px > 0 else None
    except Exception:
        return None

def fetch_ohlc_daily(ticker: str, lookback_days: int = 30) -> pd.DataFrame:
    """
    OHLC diario. 1) yfinance con sesión propia;
    2) fallback: Stooq (diario) si Yahoo falla.
    """
    # 1) Yahoo
    try:
        sess = _yf_session()
        df = yf.download(
            ticker, period=f"{lookback_days}d", interval="1d",
            auto_adjust=True, progress=False, session=sess
        )
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
    except Exception:
        pass

    # 2) Fallback Stooq (sin intradía, solo diario)
    try:
        import pandas_datareader.data as web
        df = web.DataReader(ticker, "stooq")  # devuelve del más reciente hacia atrás
        df = df.sort_index()
        # homogeneizamos nombres
        df = df.rename(columns=str.title)
        return df.tail(lookback_days)
    except Exception:
        return pd.DataFrame()

def fetch_volume_today_and_avg20(ticker: str) -> tuple[int, float]:
    """
    Volumen de hoy y promedio 20d con Yahoo. Si falla, calcula con diario (fallback).
    """
    try:
        sess = _yf_session()
        hist = yf.Ticker(ticker, session=sess).history(period="1mo", interval="1d", auto_adjust=True)
        if isinstance(hist, pd.DataFrame) and not hist.empty and "Volume" in hist.columns:
            vol_today = int(hist["Volume"].iloc[-1])
            ave20 = float(hist["Volume"].tail(20).mean())
            return vol_today, ave20
    except Exception:
        pass

    # Fallback con fetch_ohlc_daily
    df = fetch_ohlc_daily(ticker, 30)
    if not df.empty and "Volume" in df.columns:
        vol_today = int(df["Volume"].iloc[-1])
        ave20 = float(df["Volume"].tail(20).mean())
        return vol_today, ave20
    return 0, 0.0

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
