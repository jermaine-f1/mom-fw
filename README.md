# 📊 CIO Momentum Dashboard

A Python-powered momentum investing dashboard that fetches live ETF data from Yahoo Finance and generates an interactive HTML report for portfolio construction.

## Overview

This tool implements a **Quality Momentum** strategy that goes beyond simple price returns. It ranks ETFs using a composite score that balances:

- **Sortino Ratio** (40%) — Risk-adjusted returns focusing on downside volatility
- **Weeks Down** (25%) — Trend weakening detection over 12-week window
- **Z-Score Penalty** (20%) — Bubble/extension detection relative to 200-day MA
- **Slope** (15%) — Trend strength and consistency

## Features

- 📡 **Live Data** — Fetches real-time prices from Yahoo Finance
- 🎯 **Quality Scoring** — Multi-factor ranking beyond raw momentum
- 🔗 **Correlation Filtering** — Builds diversified portfolios with low pairwise correlation
- ⚙️ **Configurable Rules** — Adjust weights, thresholds, and filters in the dashboard
- 📱 **Responsive UI** — Dark-themed dashboard that works on desktop and mobile
- 📄 **CSV Input** — Customize your ETF universe via simple CSV file

## Installation

```bash
pip install -r requirements.txt
```

## Usage

1. Edit `etf_universe.csv` to customize your ETF watchlist (optional)
2. Run the generator:

```bash
python generate_cio_dashboard.py
```

3. Open `cio_momentum_dashboard_live.html` in any browser

## ETF Universe CSV

The script reads from `etf_universe.csv` in the same folder. Required columns:

| Column | Description | Example |
|--------|-------------|---------|
| `ticker` | ETF symbol | SPY |
| `sector` | Sector/category classification | US Equity |
| `country` | Geographic region | US |

If the CSV doesn't exist, a sample file with 60+ ETFs is auto-generated.

### Example CSV

```csv
ticker,sector,country
SPY,US Equity,US
QQQ,US Tech,US
EEM,EM Broad,Multi
GLD,Gold,Global
```

## Default ETF Universe

The sample CSV covers 60+ ETFs across:

| Category | Examples |
|----------|----------|
| US Equity | SPY, QQQ, IWM, DIA |
| Sectors | XLK, XLF, XLV, XLE, XLI |
| Semiconductors | SMH, SOXX |
| International | EFA, EEM, INDA, FXI, EWJ |
| Commodities | GLD, SLV, GDX, URA, COPX |
| Fixed Income | TLT, IEF, LQD, HYG |
| Thematic | ARKK, TAN, ICLN, JETS |

## Strategy Rules

### BUY Signals
1. Quality Score ≥ 55
2. Price above MA-30 AND MA-60
3. Z-Score < 4 (not in bubble territory)
4. Low correlation to existing holdings

### SELL Signals
1. Z-Score > 4 (extreme extension)
2. Price breaks below MA-30 or MA-60
3. Weeks Down ≥ 8 of 12
4. Quality Score drops below 40

### Portfolio Construction
- Target 6–10 positions
- Equal weight (no position > 15%)
- Max pairwise correlation: 0.70
- Diversify across countries and sectors

## Dashboard Tabs

| Tab | Description |
|-----|-------------|
| **Strategy** | Core principles and quality score methodology |
| **Signals** | Full ETF ranking with BUY/SELL/HOLD signals |
| **Portfolio** | Recommended holdings with correlation filtering |
| **Rules** | Configurable settings for weights and thresholds |

## Metrics Explained

| Metric | Description |
|--------|-------------|
| **6M Return** | Price change over trailing 126 days |
| **Sortino** | Annualized return ÷ downside deviation |
| **Weeks Down** | Negative weeks in last 12-week period |
| **Z-Score** | Current price deviation from 200-day MA (normalized) |
| **Slope** | Linear regression slope of 6-month price trend |
| **MA Quality** | Count of MAs price is above (30/60/200) |

## Configuration

### ETF Universe
Edit `etf_universe.csv` to add/remove tickers. Each row needs:
- `ticker` — Valid Yahoo Finance symbol
- `sector` — Your classification (used for diversification)
- `country` — Geographic region (used for diversification)

### Script Settings
Edit `generate_cio_dashboard.py` to customize:

```python
RISK_FREE_RATE = 0.045    # For Sortino calculation (currently ~4.5%)
```

## Output

The generated HTML file is self-contained with:
- Embedded Tailwind CSS via CDN
- All ETF data and correlations in JavaScript
- No external dependencies for viewing

## License

MIT

## Disclaimer

This tool is for educational and research purposes only. It does not constitute financial advice. Always do your own due diligence before making investment decisions.