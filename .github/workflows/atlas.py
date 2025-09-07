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

# FX override (si no está, se usa USDMXN=X)
FX_OVERRIDE = os.getenv("FX_RATE", "").strip()

# =========================
# Utilidades
# =========================
def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def send_telegram(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        log("⚠️ TELEGRAM no configurado (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID).")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            log(f"⚠️ Telegram error {r.status_code}: {r.text}")
        else:
            log("✅ Telegram enviado")
    except Exception as e:
        log(f"❌ Error enviando a Telegram: {e}")

def load_portfolio():
    # Espera un archivo portfolio.json con {"stocks": ["CYTK", ...]}
    path = "portfolio.json"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            tickers = data.get("stocks", [])
            if isinstance(tickers, list) and tickers:
                return [t.upper() for t in tickers]
        except Exception as e:
            log(f"⚠️ No se pudo leer portfolio.json: {e}")
    # fallback
    return ["CYTK"]

def safe_download(ticker: str, period="1d", interval="1m", tries=2):
    """
    Descarga con reintentos y valida DataFrame no vacío y columnas esperadas.
    """
    for i in range(tries):
        try:
            df = yf.download(
                ticker, period=period, interval=interval,
                progress=False, prepost=True, auto_adjust=False
            )
            if isinstance(df, pd.DataFrame) and not df.empty:
                # Algunas veces yfinance devuelve columnas multi-index
                if isinstance(df.columns, pd.MultiIndex):
                    # Tomamos la columna 'Close' del primer nivel
                    close = df["Close"]
                    if isinstance(close, pd.DataFrame):
                        # Si hay múltiples, tomar primera serie
                        close = close.iloc[:, 0]
                    df_simple = pd.DataFrame({
                        "Open":  df["Open"].iloc[:, 0] if isinstance(df["Open"],  pd.DataFrame) else df["Open"],
                        "High":  df["High"].iloc[:, 0] if isinstance(df["High"],  pd.DataFrame) else df["High"],
                        "Low":   df["Low"].iloc[:, 0]  if isinstance(df["Low"],   pd.DataFrame) else df["Low"],
                        "Close": close,
                        "Volume": df["Volume"].iloc[:, 0] if isinstance(df["Volume"], pd.DataFrame) else df["Volume"],
                    })
                    df = df_simple
                # Validar columnas
                needed = {"Open", "High", "Low", "Close", "Volume"}
                if needed.issubset(set(df.columns)):
                    return df
            log(f"Intento {i+1}/{tries}: descarga vacía para {ticker}")
        except Exception as e:
            log(f"Intento {i+1}/{tries}: error descargando {ticker}: {e}")
        time.sleep(1.5)
    return pd.DataFrame()

def get_last_price_volume(ticker: str):
    """
    Devuelve (last_price, vol_today, vol20_avg).
    vol20_avg se calcula con datos diarios 6m para aproximar la media 20d.
    """
    intr = safe_download(ticker, period="1d", interval="1m")
    if intr.empty:
        raise RuntimeError(f"No se pudo obtener intradía de {ticker}")

    last_row = intr.iloc[-1]
    last_price = float(last_row["Close"])

    daily = safe_download(ticker, period="6mo", interval="1d")
    if daily.empty:
        raise RuntimeError(f"No se pudo obtener diarios de {ticker}")

    vol_today = int(daily["Volume"].iloc[-1])
    vol20_avg = float(daily["Volume"].tail(20).mean())

    return last_price, vol_today, vol20_avg

def get_fx_usdmxn() -> float:
    if FX_OVERRIDE:
        try:
            return float(FX_OVERRIDE)
        except:
            pass
    fx = safe_download("USDMXN=X", period="1d", interval="1m")
    if not fx.empty:
        return float(fx["Close"].iloc[-1])
    # Fallback razonable
    log("⚠️ No se pudo obtener USDMXN=X, usando 18.5 como fallback")
    return 18.5

def calc_pnl(price: float, cost: float, shares: int, fx: float):
    pnl_usd = (price - cost) * shares
    pnl_mxn = pnl_usd * fx
    return pnl_usd, pnl_mxn

def decide_action(price: float, vol_today: float, vol20_avg: float):
    """
    Aplica reglas A/B/C. Devuelve (acción, razón)
    """
    # C primero (protección)
    if price <= STOP_ALL:
        return "SELL ALL", f"C: precio <= ${STOP_ALL:.2f}"
    # A
    if price >= TAKE_PROFIT:
        # Podrías afinar: si >= 55 y volumen alto, activar B
        if price >= MOMO_PRICE and vol_today >= MOMO_VOL_X * vol20_avg:
            return "SELL 50% / TRAIL", f"B: precio >= ${MOMO_PRICE:.2f} y vol >= {int(MOMO_VOL_X*100)}% media 20d"
        return "TAKE-PROFIT PARTIAL", f"A: precio >= ${TAKE_PROFIT:.2f}"
    # B puro (momo sin tocar aún A)
    if price >= MOMO_PRICE and vol_today >= MOMO_VOL_X * vol20_avg:
        return "SELL 50% / TRAIL", f"B: precio >= ${MOMO_PRICE:.2f} y vol >= {int(MOMO_VOL_X*100)}% media 20d"
    # Default
    return "HOLD", "Ninguna condición cumplida."

def build_report_line(ticker: str, price: float, vol_today: int, vol20_avg: float):
    return f"{ticker}: ${price:.2f} | Vol: {vol_today:,} vs prom20d: {int(vol20_avg):,}"

# =========================
# Main
# =========================
def main():
    tickers = load_portfolio()
    fx = get_fx_usdmxn()

    log(f"Portafolio: {tickers}")
    log(f"FX USD/MXN: {fx:.4f}")

    lines = []
    cytk_price = None
    cytk_vol_today = None
    cytk_vol20 = None

    for t in tickers:
        try:
            price, vol_today, vol20_avg = get_last_price_volume(t)
            lines.append(build_report_line(t, price, vol_today, vol20_avg))
            if t.upper() == "CYTK":
                cytk_price = price
                cytk_vol_today = vol_today
                cytk_vol20 = vol20_avg
        except Exception as e:
            lines.append(f"{t}: ❌ {e}")

    # Si CYTK está en la lista, calcula P/L y reglas
    action = "HOLD"
    reason = "—"
    pnl_usd = pnl_mxn = 0.0

    if "CYTK" in [t.upper() for t in tickers] and cytk_price is not None:
        pnl_usd, pnl_mxn = calc_pnl(cytk_price, CYTK_COST, CYTK_SHARES, fx)
        action, reason = decide_action(cytk_price, cytk_vol_today, cytk_vol20)

    # Mensaje
    now = datetime.now(timezone.utc).astimezone()
    header = "📊 REPORTE ATLAS"
    when = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    body = "\n".join(lines)

    if cytk_price is not None:
        body += (
            f"\n\nCYTK P/L: ${pnl_usd:,.2f} USD | ${pnl_mxn:,.2f} MXN"
            f"\nReglas:  A) {TAKE_PROFIT:.2f}  |  B) {MOMO_PRICE:.2f} y {int(MOMO_VOL_X*100)}% vol  |  C) {STOP_ALL:.2f}"
        )

    footer = f"\n\n✅ ACCIÓN: {action}\nRazón: {reason}"

    msg = f"{header}\n{when}\n\n{body}{footer}"

    print("\n" + msg + "\n")
    send_telegram(msg)

if __name__ == "__main__":
    main()
