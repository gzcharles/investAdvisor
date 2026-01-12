# AI Crypto Advisor

Based on DeepSeek and Binance data, this Streamlit application provides crypto investment advice.

## Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the app:
   ```bash
   streamlit run crypto_advisor.py
   ```

## Deployment

### Option 1: Streamlit Community Cloud (Recommended)

Streamlit Community Cloud is the easiest way to deploy Streamlit apps.

1. Push this code to a GitHub repository.
2. Go to [share.streamlit.io](https://share.streamlit.io/).
3. Connect your GitHub account.
4. Select the repository and the main file (`crypto_advisor.py`).
5. Click "Deploy".

### Option 2: Docker (Render/Railway/Zeabur)

If you prefer container-based deployment:

1. Create a `Dockerfile`.
2. Deploy to a platform that supports Docker.

### Note on Vercel

Vercel is designed for serverless functions and static sites. Streamlit apps require a persistent WebSocket connection, which is not supported by Vercel's serverless environment. Therefore, deploying this app directly to Vercel is **not recommended** as it will likely timeout or fail to connect.
