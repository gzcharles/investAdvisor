import streamlit as st
import ccxt
import pandas as pd
import plotly.graph_objects as go
from openai import OpenAI
import datetime

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
st.markdown(f"当前分析对象: **{symbol}** (永续合约) | 时间跨度: 近 {days_back} 天")

# 1. 自动获取数据
proxies = None
if use_proxy:
    proxies = {
        'http': http_proxy,
        'https': https_proxy
    }

with st.spinner("正在自动获取市场数据..."):
    df, error = fetch_binance_data(symbol, timeframe, days_back, proxies)

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
        yaxis_title='价格 (USDT)',
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
                st.markdown(analysis_result)

# 页脚
st.markdown("---")
st.caption("免责声明：本应用提供的分析建议仅供参考，不构成投资建议。市场有风险，投资需谨慎。")
