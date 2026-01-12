import ccxt
import pandas as pd

try:
    print("Initializing ccxt...")
    config = {
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
        }
    }
    
    exchange = ccxt.binance(config)
    
    # URL Overrides
    exchange.urls['api'] = {
        'public': 'https://fapi.binance.com/fapi/v1',
        'private': 'https://fapi.binance.com/fapi/v1',
        'fapiPublic': 'https://fapi.binance.com/fapi/v1',
        'fapiPrivate': 'https://fapi.binance.com/fapi/v1',
    }
    
    # Manual Market Injection
    symbol = "BTC/USDT"
    market_id = symbol.replace('/', '')
    exchange.markets = {
        symbol: {
            'id': market_id,
            'symbol': symbol,
            'base': symbol.split('/')[0],
            'quote': symbol.split('/')[1],
            'active': True,
            'type': 'future',
            'spot': False,
            'future': True,
            'swap': True, 
            'linear': True,
            'inverse': False,
            'contract': True,
            'option': False,
            'margin': False,
            'precision': {
                'amount': 3,
                'price': 2
            },
            'limits': {
                'amount': {
                    'min': 0.001,
                    'max': 1000
                },
                'price': {
                    'min': 0.01,
                    'max': 1000000
                },
                'cost': {
                    'min': 5,
                    'max': 1000000
                }
            },
            'info': {} # Add empty info
        }
    }
    exchange.markets_by_id = {
        market_id: exchange.markets[symbol]
    }
    
    print("Fetching OHLCV...")
    # Try a simple fetch first
    days = 3
    timeframe = '1h'
    since = exchange.milliseconds() - days * 24 * 60 * 60 * 1000
    
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)
    
    print(f"Fetched {len(ohlcv)} records.")
    if len(ohlcv) > 0:
        print("First record:", ohlcv[0])
        print("Last record:", ohlcv[-1])

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
