# Core broad-market benchmark
BENCHMARK = "SPY"

# Sector ETFs: used to identify today's hot sectors
SECTOR_ETFS = {
    "Technology": "XLK",
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}

# Industry / theme ETFs: used to identify hot industries
# You can add/remove ETFs based on your watchlist.
INDUSTRY_ETFS = {
    "Semiconductors": "SMH",
    "Software": "IGV",
    "Cybersecurity": "HACK",
    "Cloud Computing": "SKYY",
    "Internet": "FDN",
    "Biotech": "XBI",
    "Pharma": "PPH",
    "Regional Banks": "KRE",
    "Broker Dealers": "IAI",
    "Insurance": "KIE",
    "Homebuilders": "ITB",
    "Retail": "XRT",
    "Transportation": "IYT",
    "Aerospace & Defense": "ITA",
    "Oil & Gas Exploration": "XOP",
    "Oil Services": "OIH",
    "Metals & Mining": "XME",
    "Gold Miners": "GDX",
    "Clean Energy": "ICLN",
    "Solar": "TAN",
    "Uranium": "URA",
    "REITs": "VNQ",
}

# Ranking controls
MIN_PRICE = 10
MIN_DOLLAR_VOLUME = 20_000_000
TOP_SECTORS = 3
TOP_INDUSTRIES = 5
TOP_STOCKS_PER_HOT_SECTOR = 8
TOP_STOCKS_OVERALL = 20

# Target Pacific times. GitHub cron runs in UTC, so the workflow fires at both
# PST and PDT equivalents. The Python script sends only when local Pacific time matches this list.
TARGET_PACIFIC_TIMES = {"05:00", "06:30", "09:00", "11:00"}

# Weekdays only by default
WEEKDAYS_ONLY = True
