import streamlit as st
import ccxt
import pandas as pd
import plotly.graph_objects as go
from openai import OpenAI
import datetime
import requests

# 设置页面配置
st.set_page_config(
    page_title="AI 加密货币投资顾问",
    page_icon="📈",
    layout="wide"
)

# 侧边栏配置
st.sidebar.title("配置")

# DeepSeek API 配置
st.sidebar.subheader("AI 模型配置")
api_key = st.sidebar.text_input("DeepSeek API Key", type="password", help="请输入您的 DeepSeek API Key")
base_url = st.sidebar.text_input("API Base URL", value="https://api.deepseek.com")
model_name = st.sidebar.text_input("模型名称", value="deepseek-chat")

# 交易对配置
st.sidebar.subheader("交易数据配置")
symbol = st.sidebar.text_input("交易对 (Symbol)", value="BTC/USDT")
timeframe = st.sidebar.selectbox("时间粒度", ["1h", "4h", "1d"], index=0)
days_back = st.sidebar.slider("获取数据天数", min_value=1, max_value=7, value=3)
st.sidebar.subheader("数据源")
data_source = st.sidebar.selectbox("数据源", ["Binance Futures", "CoinGecko"], index=0)
auto_switch = st.sidebar.checkbox("无法访问币安时自动切换", value=True)

if "analysis_result" not in st.session_state:
    st.session_state["analysis_result"] = None
if "chat_messages" not in st.session_state:
    st.session_state["chat_messages"] = []

# 网络代理配置
st.sidebar.subheader("网络设置")
use_proxy = st.sidebar.checkbox("使用代理", value=True)
http_proxy = st.sidebar.text_input("HTTP 代理", value="http://127.0.0.1:8001", disabled=not use_proxy)
https_proxy = st.sidebar.text_input("HTTPS 代理", value="http://127.0.0.1:8001", disabled=not use_proxy)

if st.sidebar.button("测试连接"):
    test_proxies = None
    if use_proxy:
        test_proxies = {
            'http': http_proxy,
            'https': https_proxy
        }
    try:
        # 测试连接
        test_exchange = ccxt.binance({
            'options': {'defaultType': 'future'},
            'proxies': test_proxies,
            'timeout': 5000
        })
        test_exchange.fetch_time()
        st.sidebar.success("连接成功！")
    except Exception as e:
        st.sidebar.error(f"连接失败: {str(e)}")

# 缓存数据获取函数
@st.cache_data(ttl=300)
def fetch_binance_data(symbol, timeframe, days, proxies=None):
    try:
        config = {
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',  # 永续合约
            }
        }
        if proxies:
            config['proxies'] = proxies
            
        exchange = ccxt.binance(config)
        
        # 强制只使用期货 API，避免访问 Spot API (api.binance.com)
        # 必须保留 fapiPublic/fapiPrivate，否则 fetch_ohlcv 无法找到对应的 URL
        exchange.urls['api'] = {
            'public': 'https://fapi.binance.com/fapi/v1',
            'private': 'https://fapi.binance.com/fapi/v1',
            'fapiPublic': 'https://fapi.binance.com/fapi/v1',
            'fapiPrivate': 'https://fapi.binance.com/fapi/v1',
        }
        
        # 手动注入市场数据，欺骗 ccxt 认为市场已加载，从而跳过 exchangeInfo 请求
        # 针对 Binance Futures，BTC/USDT 对应的 id 是 BTCUSDT
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
                'inverse': False,  # USDT 合约通常是正向合约 (linear)，不是反向合约 (inverse)
                'contract': True,
                'option': False,
                'margin': False,
            }
        }
        exchange.markets_by_id = {
            market_id: exchange.markets[symbol]
        }
        
        # 计算起始时间
        since = exchange.milliseconds() - days * 24 * 60 * 60 * 1000
        
        # 直接调用 fetch_ohlcv，此时 markets 已有数据，不会触发 load_markets
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)
        
        if not ohlcv:
            return None, "未获取到数据，请检查交易对名称是否正确。"
            
        # 转换为 DataFrame
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        return df, None
    except Exception as e:
        return None, str(e)

@st.cache_data(ttl=300)
def fetch_coingecko_data(symbol, timeframe, days, proxies=None):
    try:
        base, quote = symbol.split('/')
        vs_map = {'USDT': 'usd', 'USD': 'usd', 'USDC': 'usd', 'CNY': 'cny', 'EUR': 'eur'}
        vs_currency = vs_map.get(quote.upper(), 'usd')
        mapping = {
            'BTC': 'bitcoin', 'ETH': 'ethereum', 'BNB': 'binancecoin', 'SOL': 'solana',
            'ADA': 'cardano', 'XRP': 'ripple', 'DOGE': 'dogecoin', 'TRX': 'tron',
            'DOT': 'polkadot', 'AVAX': 'avalanche', 'LINK': 'chainlink', 'MATIC': 'polygon'
        }
        coin_id = mapping.get(base.upper())
        if not coin_id:
            r_list = requests.get(
                'https://api.coingecko.com/api/v3/coins/list',
                params={'include_platform': 'false'},
                proxies=proxies,
                timeout=8000
            )
            r_list.raise_for_status()
            items = r_list.json()
            coin_id = next((i['id'] for i in items if i.get('symbol', '').lower() == base.lower()), None)
        if not coin_id:
            return None, "无法解析交易对到 CoinGecko 资产。"
        r = requests.get(
            f'https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart',
            params={'vs_currency': vs_currency, 'days': days},
            proxies=proxies,
            timeout=10000
        )
        r.raise_for_status()
        data = r.json()
        prices = data.get('prices', [])
        volumes = data.get('total_volumes', [])
        if not prices:
            return None, "未获取到 CoinGecko 市场数据。"
        df_p = pd.DataFrame(prices, columns=['timestamp', 'price'])
        df_v = pd.DataFrame(volumes, columns=['timestamp', 'volume'])
        df = pd.merge(df_p, df_v, on='timestamp', how='left')
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        freq_map = {'1h': '1H', '4h': '4H', '1d': '1D'}
        freq = freq_map.get(timeframe, '1H')
        rs = df.set_index('timestamp').resample(freq).agg({'price': ['first', 'max', 'min', 'last'], 'volume': 'sum'})
        rs.columns = ['open', 'high', 'low', 'close', 'volume']
        rs = rs.dropna()
        rs = rs.reset_index()
        return rs[['timestamp', 'open', 'high', 'low', 'close', 'volume']], None
    except Exception as e:
        return None, str(e)

# AI 分析函数
def analyze_market(api_key, base_url, model, df, symbol):
    if not api_key:
        return "请先在左侧侧边栏输入 DeepSeek API Key。"
    
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    # 准备数据摘要，避免 token 过多
    # 取最近的 N 条数据
    recent_data = df.tail(24).to_string(index=False)
    
    current_price = df['close'].iloc[-1]
    
    prompt = f"""
    你是专业的加密货币交易分析师。请根据以下 {symbol} 的近期市场数据（时间周期：{timeframe}）进行分析。
    当前价格: {current_price}
    
    近期数据 (OHLCV):
    {recent_data}
    
    请完成以下任务：
    1. 分析当前的市场趋势（上涨、下跌或震荡）。
    2. 识别关键的支撑位和阻力位。
    3. 结合成交量变化分析市场情绪。
    4. 给出明确的操作建议：【做多 / 做空 / 观望】。
    5. 如果建议操作，请给出具体的【入场位】、【止损位】和【止盈位】。
    
    请用简洁专业的语言回答。
    """
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个资深的金融交易分析师，擅长技术分析和加密货币市场。"},
                {"role": "user", "content": prompt}
            ],
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 分析请求失败: {str(e)}"

# 主界面
st.title("📈 AI 加密货币投资顾问 (DeepSeek Powered)")
st.markdown(f"当前分析对象: **{symbol}** | 时间跨度: 近 {days_back} 天")

# 1. 自动获取数据
proxies = None
if use_proxy:
    proxies = {
        'http': http_proxy,
        'https': https_proxy
    }

with st.spinner("正在自动获取市场数据..."):
    if data_source == "Binance Futures":
        df, error = fetch_binance_data(symbol, timeframe, days_back, proxies)
        if error and auto_switch:
            df, cg_error = fetch_coingecko_data(symbol, timeframe, days_back, proxies)
            if df is not None:
                error = None
                st.info("已自动切换到 CoinGecko 数据源。")
            else:
                error = cg_error
    else:
        df, error = fetch_coingecko_data(symbol, timeframe, days_back, proxies)

if error:
    st.error(f"数据获取失败: {error}")
else:
    # 2. 展示数据概览
    st.success(f"已更新 {len(df)} 条 K 线数据")
    
    # 绘制 K 线图
    fig = go.Figure(data=[go.Candlestick(x=df['timestamp'],
                    open=df['open'],
                    high=df['high'],
                    low=df['low'],
                    close=df['close'])])
    
    fig.update_layout(
        title=f'{symbol} K线图 ({timeframe})',
        yaxis_title='价格',
        xaxis_title='时间',
        xaxis_rangeslider_visible=False
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # 展示最近数据表格
    with st.expander("查看详细数据"):
        st.dataframe(df.sort_values('timestamp', ascending=False))
        
    # 3. AI 分析
    st.divider()
    st.subheader("🤖 DeepSeek AI 投资建议")
    
    if st.button("开始 AI 分析", type="primary"):
        if not api_key:
            st.warning("⚠️ 请在侧边栏输入 DeepSeek API Key 以获取 AI 建议。")
        else:
            with st.spinner("DeepSeek 正在思考中..."):
                analysis_result = analyze_market(api_key, base_url, model_name, df, symbol)
                st.session_state["analysis_result"] = analysis_result
                st.session_state["chat_messages"] = []

    # 显示分析结果 (如果存在)
    if st.session_state["analysis_result"]:
        st.markdown(st.session_state["analysis_result"])

    st.divider()
    st.subheader("💬 与 DeepSeek 对话")
    if not api_key:
        st.warning("⚠️ 请在侧边栏输入 DeepSeek API Key 以使用对话功能。")
    elif st.session_state["analysis_result"] is None:
        st.info("请先点击上方按钮生成一份分析，再开始对话。")
    else:
        # 使用固定高度容器包裹聊天记录
        with st.container(height=500):
            for msg in st.session_state["chat_messages"]:
                if msg["role"] == "user":
                    with st.chat_message("user"):
                        st.markdown(msg["content"])
                else:
                    with st.chat_message("assistant"):
                        st.markdown(msg["content"])
            
        user_question = st.chat_input("就当前市场分析继续提问...")
        if user_question:
            st.session_state["chat_messages"].append({"role": "user", "content": user_question})
            # 这里的 user 消息因为在 container 外面渲染，可能会有一瞬间不在滚动区域内
            # 但下一帧重绘时会在 container 内显示。
            # 为了更好的体验，我们直接在 container 内写一个临时显示逻辑不太容易，
            # 依赖 Streamlit 的 rerun 机制是标准做法。
            # 当用户输入后，st.chat_input 会触发 rerun，代码会从头执行。
            # 执行到上面的 for msg in ... 时，新消息就会显示在 container 里了。
            
            with st.spinner("DeepSeek 正在回答..."):
                client = OpenAI(api_key=api_key, base_url=base_url)
                history = [
                    {
                        "role": "system",
                        "content": "你是一个资深的金融交易分析师，擅长技术分析和加密货币市场。回答要结合之前的分析结论，并保持逻辑一致。"
                    },
                    {
                        "role": "user",
                        "content": f"下面是你刚刚给出的关于 {symbol} 的市场分析结论：\n{st.session_state['analysis_result']}\n\n用户的追问会围绕这份分析展开，请据此回答。"
                    }
                ]
                for m in st.session_state["chat_messages"]:
                    history.append({"role": m["role"], "content": m["content"]})
                try:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=history,
                        stream=False
                    )
                    answer = response.choices[0].message.content
                except Exception as e:
                    answer = f"对话请求失败: {str(e)}"
                st.session_state["chat_messages"].append({"role": "assistant", "content": answer})
                # 强制重新运行以显示最新消息
                st.rerun()

# 页脚
st.markdown("---")
st.caption("免责声明：本应用提供的分析建议仅供参考，不构成投资建议。市场有风险，投资需谨慎。")
