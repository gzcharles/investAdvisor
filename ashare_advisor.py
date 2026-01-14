import streamlit as st
import akshare as ak
import pandas as pd
import plotly.graph_objects as go
from openai import OpenAI
import os
import datetime

# 设置页面配置
st.set_page_config(
    page_title="A股 AI 投资顾问",
    page_icon="📈",
    layout="wide"
)

# 侧边栏配置
st.sidebar.title("配置")

# DeepSeek API 配置
default_api_key = os.getenv("DEEPSEEK_API_KEY", "")
st.sidebar.subheader("AI 模型配置")
api_key = st.sidebar.text_input(
    "DeepSeek API Key",
    value=default_api_key,
    type="password",
    help="请输入您的 DeepSeek API Key"
)
base_url = st.sidebar.text_input("API Base URL", value="https://api.deepseek.com")
model_name = st.sidebar.text_input("模型名称", value="deepseek-chat")

# Session State 初始化
if "ashare_analysis_result" not in st.session_state:
    st.session_state["ashare_analysis_result"] = None
if "ashare_chat_messages" not in st.session_state:
    st.session_state["ashare_chat_messages"] = []

# 辅助函数：根据输入查找股票代码
@st.cache_data(ttl=3600)
def search_stock(keyword):
    try:
        # 获取所有A股股票列表
        stock_info_df = ak.stock_info_a_code_name()
        # 尝试完全匹配代码
        code_match = stock_info_df[stock_info_df['code'] == keyword]
        if not code_match.empty:
            return code_match.iloc[0]['code'], code_match.iloc[0]['name']
        
        # 尝试匹配名称
        name_match = stock_info_df[stock_info_df['name'].str.contains(keyword)]
        if not name_match.empty:
            # 返回第一个匹配项
            return name_match.iloc[0]['code'], name_match.iloc[0]['name']
        
        code_candidate = keyword.strip()
        if code_candidate.isdigit() and len(code_candidate) == 6:
            return code_candidate, code_candidate
        return None, None
    except Exception as e:
        code_candidate = keyword.strip()
        if code_candidate.isdigit() and len(code_candidate) == 6:
            return code_candidate, code_candidate
        return None, str(e)

# 数据获取函数
@st.cache_data(ttl=300)
def fetch_ashare_data(symbol, days):
    try:
        # 计算起始日期
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=days * 2) # 多取一些天数以确保交易日足够
        
        start_date_str = start_date.strftime("%Y%m%d")
        end_date_str = end_date.strftime("%Y%m%d")
        
        # 获取日线数据
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date_str, end_date=end_date_str, adjust="qfq")
        
        if df.empty:
            return None, "未获取到数据，请检查股票代码是否正确或近期是否停牌。"
            
        # 重命名列以符合习惯
        df = df.rename(columns={
            "日期": "timestamp",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume"
        })
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # 只取最近 N 个交易日
        df = df.tail(days)
        
        return df, None
    except Exception as e:
        return None, str(e)

# AI 分析函数
def analyze_market(api_key, base_url, model, df, symbol_name, symbol_code):
    if not api_key:
        return "请先在左侧侧边栏输入 DeepSeek API Key。"
    
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    # 准备数据摘要
    recent_data = df.to_string(index=False)
    current_price = df['close'].iloc[-1]
    
    prompt = f"""
    你是专业的 A 股证券分析师。请根据以下 {symbol_name} ({symbol_code}) 的近期市场数据（日线）进行分析。
    当前价格: {current_price}
    
    近期数据 (OHLCV):
    {recent_data}
    
    请完成以下任务：
    1. 分析当前的市场趋势（上涨、下跌或震荡）。
    2. 识别关键的支撑位和阻力位。
    3. 结合成交量变化分析主力资金动向和市场情绪。
    4. 给出明确的操作建议：【买入 / 卖出 / 持仓 / 空仓观望】。
    5. 如果建议操作，请给出具体的【参考价位】和【止损位】。
    
    请注意 A 股市场特点（T+1 交易，涨跌幅限制等），用简洁专业的语言回答。
    """
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个资深的 A 股证券分析师，擅长技术分析和基本面判断。"},
                {"role": "user", "content": prompt}
            ],
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 分析请求失败: {str(e)}"

# 主界面逻辑
st.title("📈 A股 AI 投资顾问 (DeepSeek Powered)")

col_code, col_days = st.columns([3, 1])
with col_code:
    stock_input = st.text_input("股票代码或名称", value="600519")
with col_days:
    days_back = st.slider("交易日数量", min_value=15, max_value=60, value=15)

# 1. 股票搜索与确认
real_code, real_name = search_stock(stock_input)

if not real_code:
    st.error(f"未找到代码或名称包含 '{stock_input}' 的股票，请检查输入。")
else:
    st.markdown(f"当前分析对象: **{real_name} ({real_code})** | 时间跨度: 近 {days_back} 个交易日")
    
    # 2. 获取数据
    with st.spinner("正在获取 A 股数据..."):
        df, error = fetch_ashare_data(real_code, days_back)
        
    if error:
        st.error(f"数据获取失败: {error}")
    else:
        # 3. 展示图表
        st.success(f"已更新 {len(df)} 条交易数据")
        
        fig = go.Figure(data=[go.Candlestick(x=df['timestamp'],
                        open=df['open'],
                        high=df['high'],
                        low=df['low'],
                        close=df['close'])])
        
        fig.update_layout(
            title=f'{real_name} ({real_code}) 日K线图',
            yaxis_title='价格 (CNY)',
            xaxis_title='日期',
            xaxis_rangeslider_visible=False
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("查看详细数据"):
            st.dataframe(df.sort_values('timestamp', ascending=False))
            
        # 4. AI 分析
        st.divider()
        st.subheader("🤖 DeepSeek AI 投资建议")
        
        if st.button("开始 AI 分析", type="primary"):
            if not api_key:
                st.warning("⚠️ 请在侧边栏输入 DeepSeek API Key 以获取 AI 建议。")
            else:
                with st.spinner("DeepSeek 正在思考中..."):
                    analysis_result = analyze_market(api_key, base_url, model_name, df, real_name, real_code)
                    st.session_state["ashare_analysis_result"] = analysis_result
                    st.session_state["ashare_chat_messages"] = []
        
        # 显示分析结果
        if st.session_state["ashare_analysis_result"]:
            st.markdown(st.session_state["ashare_analysis_result"])
            
        # 5. 对话功能
        st.divider()
        st.subheader("💬 与 DeepSeek 对话")
        
        if not api_key:
             st.warning("⚠️ 请在侧边栏输入 DeepSeek API Key 以使用对话功能。")
        elif st.session_state["ashare_analysis_result"] is None:
            st.info("请先点击上方按钮生成一份分析，再开始对话。")
        else:
            with st.container(height=500):
                for msg in st.session_state["ashare_chat_messages"]:
                    if msg["role"] == "user":
                        with st.chat_message("user"):
                            st.markdown(msg["content"])
                    else:
                        with st.chat_message("assistant"):
                            st.markdown(msg["content"])
            
            user_question = st.chat_input("就当前 A 股分析继续提问...")
            if user_question:
                st.session_state["ashare_chat_messages"].append({"role": "user", "content": user_question})
                
                with st.spinner("DeepSeek 正在回答..."):
                    client = OpenAI(api_key=api_key, base_url=base_url)
                    history = [
                        {
                            "role": "system",
                            "content": "你是一个资深的 A 股证券分析师。回答要结合之前的分析结论，并保持逻辑一致。"
                        },
                        {
                            "role": "user",
                            "content": f"下面是你刚刚给出的关于 {real_name} ({real_code}) 的市场分析结论：\n{st.session_state['ashare_analysis_result']}\n\n用户的追问会围绕这份分析展开，请据此回答。"
                        }
                    ]
                    for m in st.session_state["ashare_chat_messages"]:
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
                    
                    st.session_state["ashare_chat_messages"].append({"role": "assistant", "content": answer})
                    st.rerun()

# 页脚
st.markdown("---")
st.caption("免责声明：本应用提供的分析建议仅供参考，不构成投资建议。股市有风险，入市需谨慎。")
