import ccxt

print("CCXT Version:", ccxt.__version__)

try:
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
        }
    })
    # Manually check the urls
    print("API URLs:", exchange.urls['api'])
    
    # Try to see what load_markets does (dry run if possible, but here we just want to see where it requests)
    # We can't easily see the request without enabling verbose mode
    exchange.verbose = True
    try:
        exchange.load_markets()
    except Exception as e:
        print("Error during load_markets:", e)

except Exception as e:
    print("Init Error:", e)
