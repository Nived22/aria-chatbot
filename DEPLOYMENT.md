# Aria Chatbot — Deployment Guide

## Step 1: AWS Account Setup

1. Go to https://aws.amazon.com → Create Account (use university email)
2. Choose Free Tier

### Create DynamoDB Table
- AWS Console → DynamoDB → Create Table
- Table name: `shopsmart-customers`
- Partition key: `customer_id` (String)
- Click Create

### Create IAM User
- AWS Console → IAM → Users → Create User
- Username: `shopsmart-chatbot`
- Attach policy: `AmazonDynamoDBFullAccess`
- Create User → Security Credentials → Create Access Key
- Choose "Local code" → **Download CSV and save it safely**

### Add customers to DynamoDB
- DynamoDB → Tables → shopsmart-customers → Explore items → Create item
- Add fields: customer_id, name, total_spent, order_count, is_vip, last_order


## Step 2: GitHub Setup

```bash
cd ~/Desktop/EMOTION_CHATBOT_COMPLETE

git init
git add .
git commit -m "Initial commit — Aria emotion-aware chatbot"

# Create repo on github.com first, then:
git remote add origin https://github.com/YOURUSERNAME/aria-chatbot.git
git push -u origin main
```


## Step 3: Deploy on Streamlit Cloud (free)

1. Go to https://share.streamlit.io
2. Sign in with GitHub
3. Click "New app"
4. Select your repo → Branch: main → Main file: app.py
5. Click "Advanced settings" → Secrets → paste:

```toml
ANTHROPIC_API_KEY = "sk-ant-your-key"
AWS_ACCESS_KEY_ID = "AKIA..."
AWS_SECRET_ACCESS_KEY = "..."
AWS_REGION = "eu-west-1"
DYNAMODB_CUSTOMER_TABLE = "shopsmart-customers"
```

6. Click Deploy → wait ~3 minutes
7. You get a URL like: `https://yourname-aria-chatbot.streamlit.app`


## Step 4: Share with testers

Send your testers this message:

> "Hi! I'm testing my MSc dissertation chatbot and would love your feedback.
> Please chat with Aria at: https://yourname-aria-chatbot.streamlit.app
> Try asking about orders, returns, or refunds. Takes 5 minutes!"

**For the backend dashboard** — deploy separately:
- Streamlit Cloud → New app → same repo → Main file: backend.py
- Share only with yourself/supervisor


## Step 5: Collect feedback

The built-in survey (Leave Feedback button) saves results automatically.
After testing, check your logs/ folder or DynamoDB for session data.


## Local testing with ngrok (alternative)

```bash
brew install ngrok
ngrok config add-authtoken YOUR_TOKEN  # free at ngrok.com

streamlit run app.py &
ngrok http 8501
# Share the https://xxxx.ngrok-free.app URL
```
