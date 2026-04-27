import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

TICKERS = ["CRCL", "COIN", "HOOD"]
END = datetime.today()
START = END - timedelta(days=730)


def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def detect_rsi_divergence(price, rsi, window=14):
    """Detect bullish/bearish RSI divergence over a rolling window."""
    signals = pd.Series("", index=price.index)
    for i in range(window, len(price)):
        p_window = price.iloc[i - window:i + 1]
        r_window = rsi.iloc[i - window:i + 1]
        p_low_idx = p_window.idxmin()
        p_high_idx = p_window.idxmax()
        # Bullish divergence: price makes lower low, RSI makes higher low
        if p_low_idx == p_window.index[-1]:
            prev_low_rsi = r_window.iloc[:-1].min()
            if rsi.iloc[i] > prev_low_rsi:
                signals.iloc[i] = "Bullish Divergence"
        # Bearish divergence: price makes higher high, RSI makes lower high
        if p_high_idx == p_window.index[-1]:
            prev_high_rsi = r_window.iloc[:-1].max()
            if rsi.iloc[i] < prev_high_rsi:
                signals.iloc[i] = "Bearish Divergence"
    return signals


def analyze_ticker(ticker):
    df = yf.download(ticker, start=START, end=END, progress=False, auto_adjust=True)
    if df.empty:
        print(f"No data for {ticker}")
        return None, []

    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()

    # Moving averages
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()

    # MA crossover signals
    df["MA_cross"] = ""
    prev_diff = df["MA20"] - df["MA50"]
    cross_up = (prev_diff > 0) & (prev_diff.shift(1) <= 0)
    cross_down = (prev_diff < 0) & (prev_diff.shift(1) >= 0)
    df.loc[cross_up, "MA_cross"] = "Golden Cross (20>50)"
    df.loc[cross_down, "MA_cross"] = "Death Cross (20<50)"

    # RSI
    df["RSI"] = compute_rsi(df["Close"])

    # RSI divergence
    df["RSI_div"] = detect_rsi_divergence(df["Close"], df["RSI"])

    # 52-week high/low proximity (within 2%)
    df["52W_High"] = df["High"].rolling(252).max()
    df["52W_Low"] = df["Low"].rolling(252).min()
    df["52W_signal"] = ""
    near_high = df["Close"] >= df["52W_High"] * 0.98
    near_low = df["Close"] <= df["52W_Low"] * 1.02
    df.loc[near_high, "52W_signal"] = "Near 52W High"
    df.loc[near_low, "52W_signal"] = "Near 52W Low"

    # Collect signals (last 30 days for recency)
    recent = df.tail(30)
    signals = []

    for date, row in recent.iterrows():
        date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)
        if row["MA_cross"]:
            signals.append({"Ticker": ticker, "Date": date_str, "Signal": row["MA_cross"], "Close": round(row["Close"], 2)})
        if row["RSI_div"]:
            signals.append({"Ticker": ticker, "Date": date_str, "Signal": row["RSI_div"], "Close": round(row["Close"], 2)})
        if row["52W_signal"]:
            signals.append({"Ticker": ticker, "Date": date_str, "Signal": row["52W_signal"], "Close": round(row["Close"], 2)})

    # Also capture the most recent RSI reading as info
    last = df.iloc[-1]
    signals.append({
        "Ticker": ticker,
        "Date": "Latest",
        "Signal": f"RSI={last['RSI']:.1f} | 52W_Hi={last['52W_High']:.2f} | 52W_Lo={last['52W_Low']:.2f}",
        "Close": round(last["Close"], 2),
    })

    return df, signals


def plot_ticker(df, ticker, ax_price, ax_rsi):
    ax_price.plot(df.index, df["Close"], label="Close", linewidth=1.5, color="#1f77b4")
    ax_price.plot(df.index, df["MA20"], label="MA20", linewidth=1, color="orange", linestyle="--")
    ax_price.plot(df.index, df["MA50"], label="MA50", linewidth=1, color="green", linestyle="--")

    # Mark crossovers
    golden = df[df["MA_cross"] == "Golden Cross (20>50)"]
    death = df[df["MA_cross"] == "Death Cross (20<50)"]
    ax_price.scatter(golden.index, golden["Close"], marker="^", color="gold", s=100, zorder=5, label="Golden Cross")
    ax_price.scatter(death.index, death["Close"], marker="v", color="red", s=100, zorder=5, label="Death Cross")

    # 52-week bands
    ax_price.plot(df.index, df["52W_High"], linestyle=":", color="purple", linewidth=0.8, label="52W High")
    ax_price.plot(df.index, df["52W_Low"], linestyle=":", color="brown", linewidth=0.8, label="52W Low")

    ax_price.set_title(f"{ticker} — Price + Indicators", fontsize=12, fontweight="bold")
    ax_price.set_ylabel("Price ($)")
    ax_price.legend(fontsize=7, loc="upper left")
    ax_price.grid(alpha=0.3)

    # RSI
    ax_rsi.plot(df.index, df["RSI"], color="purple", linewidth=1)
    ax_rsi.axhline(70, color="red", linestyle="--", linewidth=0.8, label="Overbought (70)")
    ax_rsi.axhline(30, color="green", linestyle="--", linewidth=0.8, label="Oversold (30)")
    ax_rsi.fill_between(df.index, df["RSI"], 70, where=(df["RSI"] >= 70), alpha=0.2, color="red")
    ax_rsi.fill_between(df.index, df["RSI"], 30, where=(df["RSI"] <= 30), alpha=0.2, color="green")
    ax_rsi.set_ylabel("RSI")
    ax_rsi.set_ylim(0, 100)
    ax_rsi.legend(fontsize=7)
    ax_rsi.grid(alpha=0.3)

    # Mark RSI divergence signals
    bull_div = df[df["RSI_div"] == "Bullish Divergence"]
    bear_div = df[df["RSI_div"] == "Bearish Divergence"]
    ax_rsi.scatter(bull_div.index, bull_div["RSI"], marker="^", color="green", s=60, zorder=5, label="Bull Div")
    ax_rsi.scatter(bear_div.index, bear_div["RSI"], marker="v", color="red", s=60, zorder=5, label="Bear Div")


def main():
    all_signals = []

    fig = plt.figure(figsize=(18, 14))
    fig.suptitle("Option Trading — Signal Analysis (2Y Daily)", fontsize=14, fontweight="bold")
    gs = gridspec.GridSpec(len(TICKERS) * 2, 1, hspace=0.5, height_ratios=[3, 1] * len(TICKERS))

    for i, ticker in enumerate(TICKERS):
        print(f"Fetching {ticker}...")
        df, signals = analyze_ticker(ticker)
        if df is None:
            continue
        all_signals.extend(signals)

        ax_price = fig.add_subplot(gs[i * 2])
        ax_rsi = fig.add_subplot(gs[i * 2 + 1], sharex=ax_price)
        plot_ticker(df, ticker, ax_price, ax_rsi)

    # Summary table
    signal_df = pd.DataFrame(all_signals)
    print("\n" + "=" * 70)
    print("SIGNAL SUMMARY TABLE")
    print("=" * 70)
    pd.set_option("display.max_colwidth", 60)
    pd.set_option("display.width", 120)
    print(signal_df.to_string(index=False))
    print("=" * 70)

    # Save table to CSV
    signal_df.to_csv("signals_summary.csv", index=False)
    print("\nSaved signals to signals_summary.csv")

    plt.tight_layout()
    plt.savefig("signals_chart.png", dpi=150, bbox_inches="tight")
    print("Saved chart to signals_chart.png")
    plt.show()


if __name__ == "__main__":
    main()
