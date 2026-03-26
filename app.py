# app.py — Customer Chat Interface (customer-facing only)
# Run: streamlit run app.py
import streamlit as st
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import EmotionChatbotPipeline
from aws.customer_db import is_vip_customer
from config import BOT_NAME, COMPANY_NAME

st.set_page_config(
    page_title=f"{COMPANY_NAME} Support",
    page_icon="🛍️", layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&family=DM+Serif+Display&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body, .stApp { background: #0a0a0f !important; font-family: 'DM Sans', sans-serif !important; }
#MainMenu, footer, header, .stDeployButton, [data-testid="stToolbar"] { display: none !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }
[data-testid="stAppViewContainer"] { background: #0a0a0f !important; }
[data-testid="stSidebar"] { display: none !important; }

/* ── Chat wrapper ── */
.chat-shell {
    max-width: 780px;
    margin: 0 auto;
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: #0a0a0f;
}

/* ── Header ── */
.chat-topbar {
    padding: 16px 24px;
    background: rgba(15,15,26,0.97);
    backdrop-filter: blur(20px);
    border-bottom: 1px solid rgba(255,255,255,0.07);
    display: flex;
    align-items: center;
    gap: 14px;
    position: sticky; top: 0; z-index: 99;
}
.bot-av-wrap { position: relative; }
.bot-av {
    width: 42px; height: 42px;
    background: linear-gradient(135deg,#6c63ff,#a855f7);
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 19px;
    box-shadow: 0 0 0 3px rgba(108,99,255,0.2);
}
.online-dot {
    position: absolute; bottom: 1px; right: 1px;
    width: 10px; height: 10px;
    background: #22c55e; border-radius: 50%;
    border: 2px solid #0f0f1a;
    animation: pulse-g 2s infinite;
}
.bot-info-name { font-size: 15px; font-weight: 600; color: #fff; line-height:1.2; }
.bot-info-status { font-size: 12px; color: #22c55e; }
.vip-tag {
    margin-left: auto;
    background: rgba(255,215,0,0.12);
    border: 1px solid rgba(255,215,0,0.3);
    color: #ffd700;
    font-size: 11px; font-weight: 600;
    padding: 3px 10px; border-radius: 20px;
}

/* ── Messages ── */
.msgs-area { flex:1; overflow-y:auto; padding: 24px 24px 8px; }

.msg-row { display:flex; gap:10px; margin-bottom:18px; animation: fadein 0.25s ease; }
.msg-row.user { flex-direction: row-reverse; }

.av {
    width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px; font-weight: 600;
}
.av.bot { background: linear-gradient(135deg,#6c63ff,#a855f7); color:#fff; font-size:16px; }
.av.usr { background: #1e293b; color: #94a3b8; }

.bubble {
    max-width: 65%;
    min-width: 120px;
    padding: 12px 16px;
    font-size: 14.5px; line-height: 1.65;
    word-break: normal;
    overflow-wrap: break-word;
    white-space: normal;
    hyphens: none;
}
.bubble.usr {
    min-width: 120px;
    max-width: 65%;
}
.bubble.bot {
    background: #15152a;
    color: #dde1f0;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 4px 18px 18px 18px;
}
.bubble.bot.empathetic {
    background: linear-gradient(135deg,#1a163a,#15152a);
    border-color: rgba(108,99,255,0.25);
}
.bubble.usr {
    background: linear-gradient(135deg,#6c63ff,#7c3aed);
    color: #fff;
    border-radius: 18px 4px 18px 18px;
    box-shadow: 0 4px 18px rgba(108,99,255,0.28);
    word-break: break-word; overflow-wrap: anywhere;
}
.bubble.handover {
    background: linear-gradient(135deg,#1f0f0f,#1a1010);
    border: 1px solid rgba(239,68,68,0.25);
    color: #fca5a5;
    border-radius: 14px;
    padding: 16px 18px;
}
.handover-title { font-weight:700; color:#f87171; margin-bottom:6px; font-size:13px; }

.msg-time { font-size:11px; color:rgba(255,255,255,0.2); margin-top:4px; }

/* ── Name screen ── */
.name-screen {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0;
    background: #0a0a0f;
    padding: 40px 24px;
}
.name-logo {
    width: 72px; height: 72px;
    background: linear-gradient(135deg,#6c63ff,#a855f7);
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 32px;
    box-shadow: 0 0 0 8px rgba(108,99,255,0.12);
    margin-bottom: 20px;
}
.name-title {
    font-size: 22px; font-weight: 600; color: #fff;
    margin-bottom: 6px; text-align: center;
}
.name-sub {
    font-size: 14px; color: rgba(255,255,255,0.35);
    margin-bottom: 28px; text-align: center;
}

div[data-testid="stTextInput"] input {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(108,99,255,0.3) !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 14px !important;
    padding: 10px 14px !important;
    text-align: center !important;
}
div[data-testid="stTextInput"] input:focus {
    border-color: rgba(108,99,255,0.7) !important;
    box-shadow: 0 0 0 2px rgba(108,99,255,0.15) !important;
    outline: none !important;
}
div[data-testid="stTextInput"] input::placeholder {
    color: rgba(255,255,255,0.25) !important;
}

.typing-wrap { display:flex; gap:10px; margin-bottom:18px; }
.typing-bubble {
    background: #15152a; border: 1px solid rgba(255,255,255,0.07);
    border-radius: 4px 18px 18px 18px;
    padding: 13px 18px;
    display: flex; gap: 5px; align-items: center;
}
.td {
    width: 7px; height: 7px; border-radius: 50%;
    background: rgba(255,255,255,0.3);
    animation: bounce 1.2s infinite ease-in-out;
}
.td:nth-child(2){animation-delay:.2s}
.td:nth-child(3){animation-delay:.4s}

/* ── Handover alert banner ── */
.alert-wrap {
    background: rgba(249,115,22,0.07);
    border: 1px solid rgba(249,115,22,0.2);
    border-radius: 12px; padding: 11px 16px;
    font-size: 13px; color: #fb923c;
    margin: 4px 0 16px;
    display: flex; align-items: center; gap: 9px;
}

/* ── Quick chips ── */
.chips-label { font-size:12px; color:rgba(255,255,255,0.28); margin-bottom:10px; }
.chips-row { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:20px; }

/* ── Input bar ── */
.stChatInput > div {
    background: #15152a !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 16px !important;
}
.stChatInput textarea {
    color: #e2e8f0 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 14px !important;
}
.stChatInput textarea::placeholder { color: rgba(255,255,255,0.25) !important; }

/* ── Buttons ── */
.stButton > button {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    color: rgba(255,255,255,0.6) !important;
    border-radius: 20px !important;
    font-size: 13px !important;
    font-family: 'DM Sans', sans-serif !important;
    padding: 6px 16px !important;
    transition: all 0.18s !important;
}
.stButton > button:hover {
    background: rgba(108,99,255,0.12) !important;
    border-color: rgba(108,99,255,0.35) !important;
    color: #a78bfa !important;
}

/* ── Start chat button override ── */
[data-testid="stButton-start_chat"] > button {
    background: linear-gradient(135deg,#6c63ff,#7c3aed) !important;
    border: none !important;
    color: #fff !important;
    border-radius: 12px !important;
    font-size: 15px !important;
    font-weight: 600 !important;
    padding: 10px 32px !important;
    box-shadow: 0 4px 18px rgba(108,99,255,0.35) !important;
}

/* ── Survey card ── */
.survey-shell {
    background: linear-gradient(135deg,#0f0f1e,#15152a);
    border: 1px solid rgba(108,99,255,0.2);
    border-radius: 18px; padding: 22px; margin: 12px 0;
}
.survey-hd { font-family:'DM Serif Display',serif; font-size:17px; color:#fff; margin-bottom:4px; }
.survey-sub { font-size:12px; color:rgba(255,255,255,0.35); margin-bottom:18px; }

/* ── Scrollbar ── */
::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.1);border-radius:2px}

/* ── Animations ── */
@keyframes fadein{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:translateY(0)}}
@keyframes bounce{0%,80%,100%{transform:scale(1);opacity:.4}40%{transform:scale(1.35);opacity:1}}
@keyframes pulse-g{0%,100%{box-shadow:0 0 0 0 rgba(34,197,94,.4)}50%{box-shadow:0 0 0 4px rgba(34,197,94,0)}}

hr { border-color: rgba(255,255,255,0.06) !important; }
.stMarkdown p { color: rgba(255,255,255,0.6) !important; font-size:13px !important; }
label { color: rgba(255,255,255,0.45) !important; font-size:12px !important; }
[data-testid="stSelectbox"]>div>div {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important; color: #e2e8f0 !important;
}
</style>
""", unsafe_allow_html=True)


# ── Known VIP customers ───────────────────────────────────────────────────────
_KNOWN = {
    "james wilson":       "C001",
    "sarah chen":         "C002",
    "mohammed al-hassan": "C003",
    "emily roberts":      "C004",
    "david park":         "C005",
}


# ── Session init ──────────────────────────────────────────────────────────────
def init():
    d = {
        "pipeline": None, "messages": [], "frustration_history": [],
        "turn_labels": [], "last_result": None, "greeted": False,
        "high_value_user": False, "customer_data": None, "customer_id": None,
        # FIX: confirmed_name is set only when user clicks Start Chat
        # This prevents mid-typing reruns from defaulting to "Guest"
        "confirmed_name": "",
        "response_modes_used": [], "latencies_ms": [],
        "survey_submitted": False, "show_survey": False, "survey_data": {}
    }
    for k, v in d.items():
        if k not in st.session_state:
            st.session_state[k] = v

init()


# ── NAME GATE ─────────────────────────────────────────────────────────────────
# Only show the chat if a name has been confirmed via the Start Chat button.
# st.stop() below prevents any pipeline/chat code from running until then.
# This fixes:
#   1. "Guest" appearing mid-typing (empty string fallback no longer used)
#   2. VIP names not being recognised (lookup now only runs after full name entered)

if not st.session_state.confirmed_name:

    # Centre the name entry screen
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("""
        <div style="text-align:center;padding:60px 0 30px">
            <div style="width:72px;height:72px;background:linear-gradient(135deg,#6c63ff,#a855f7);
                border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
                font-size:32px;box-shadow:0 0 0 8px rgba(108,99,255,0.12);margin-bottom:20px">🤖</div>
            <div style="font-size:22px;font-weight:600;color:#fff;margin-bottom:6px">
                Welcome to ShopSmart Support
            </div>
            <div style="font-size:14px;color:rgba(255,255,255,0.35);margin-bottom:28px">
                Please enter your name to begin
            </div>
        </div>
        """, unsafe_allow_html=True)

        name_field = st.text_input(
            "Your name",
            placeholder="Enter your name...",
            label_visibility="collapsed",
            max_chars=40,
            key="name_input_field",
        )

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        if st.button("Start Chat →", use_container_width=True, key="start_chat"):
            entered = name_field.strip()
            if not entered:
                st.warning("Please enter your name to continue.")
            else:
                # ── Resolve customer identity ─────────────────────────────
                cid_match = _KNOWN.get(entered.lower())

                if cid_match:
                    # Known VIP — load from DynamoDB
                    is_vip, cdata = is_vip_customer(cid_match)
                    cid = cid_match
                else:
                    # Guest — build local profile with their typed name
                    cid = f"GUEST_{entered[:8].replace(' ', '_').upper()}"
                    cdata = {
                        "customer_id": cid,
                        "name":        entered,
                        "total_spent": 0.0,
                        "order_count": 0,
                        "is_vip":      False,
                        "last_order":  None,
                    }
                    is_vip = False

                # ── Commit to session state in one go ─────────────────────
                st.session_state.confirmed_name   = entered
                st.session_state.customer_id      = cid
                st.session_state.customer_data    = cdata
                st.session_state.high_value_user  = is_vip
                st.session_state.greeted          = False

                # Initialise pipeline with customer data
                st.session_state.pipeline = EmotionChatbotPipeline()
                st.session_state.pipeline.customer_data = cdata

                st.rerun()  # re-render into chat view

    # Block everything below — pipeline, greeting, chat input — until confirmed
    st.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# Everything below only executes after the name has been confirmed
# ═══════════════════════════════════════════════════════════════════════════════

# ── Ensure pipeline exists (safety net for hot-reload) ───────────────────────
if st.session_state.pipeline is None:
    st.session_state.pipeline = EmotionChatbotPipeline()
    cdata_init = st.session_state.customer_data or {}
    if cdata_init:
        st.session_state.pipeline.customer_data = cdata_init

cdata  = st.session_state.customer_data or {}
is_vip = st.session_state.high_value_user
c_name = cdata.get("name", st.session_state.confirmed_name)
c_init = c_name[0].upper() if c_name else "?"
c_spent = cdata.get("total_spent", 0)


# ── Header ────────────────────────────────────────────────────────────────────
vip_html = '<span class="vip-tag">⭐ VIP</span>' if is_vip else ""
st.markdown(f"""
<div class="chat-topbar">
    <div class="bot-av-wrap">
        <div class="bot-av">🤖</div>
        <div class="online-dot"></div>
    </div>
    <div>
        <div class="bot-info-name">{BOT_NAME} · {COMPANY_NAME}</div>
        <div class="bot-info-status">● Online — typically replies instantly</div>
    </div>
    {vip_html}
</div>
""", unsafe_allow_html=True)


# ── Greeting ──────────────────────────────────────────────────────────────────
if not st.session_state.greeted:
    greet = (
        f"Welcome back, {c_name}! 👋 As a valued customer you have priority support today. "
        f"I'm {BOT_NAME} — how can I help you?"
    ) if is_vip else (
        f"Hi {c_name}! I'm {BOT_NAME}, your {COMPANY_NAME} support assistant. "
        f"How can I help you today?"
    )
    st.markdown(f"""
    <div class="msg-row">
        <div class="av bot">🤖</div>
        <div><div class="bubble bot">{greet}</div></div>
    </div>""", unsafe_allow_html=True)
    st.session_state.greeted = True


# ── Message history ───────────────────────────────────────────────────────────
for msg in st.session_state.messages:
    role = msg["role"]
    text = msg["text"]
    mode = msg.get("mode", "normal")
    if role == "user":
        st.markdown(f"""
        <div class="msg-row user">
            <div class="av usr">{c_init}</div>
            <div><div class="bubble usr">{text}</div></div>
        </div>""", unsafe_allow_html=True)
    else:
        if mode == "handover":
            st.markdown(f"""
            <div class="msg-row">
                <div class="av bot">🤖</div>
                <div><div class="bubble handover">
                    <div class="handover-title">🚨 Connecting you to a human agent</div>
                    {text}
                </div></div>
            </div>""", unsafe_allow_html=True)
        else:
            cls = "empathetic" if "empathetic" in mode else "bot"
            st.markdown(f"""
            <div class="msg-row">
                <div class="av bot">🤖</div>
                <div><div class="bubble {cls}">{text}</div></div>
            </div>""", unsafe_allow_html=True)


# ── Agent alert (customer-friendly wording) ───────────────────────────────────
if st.session_state.last_result:
    resp = st.session_state.last_result.get("response", {})
    if resp.get("alert_agent") and not resp.get("trigger_handover"):
        st.markdown("""
        <div class="alert-wrap">
            ⚡ A support agent has been notified and is on standby if you need them.
        </div>""", unsafe_allow_html=True)


# ── Handover bundle ───────────────────────────────────────────────────────────
if st.session_state.last_result and st.session_state.last_result.get("handover_bundle"):
    bundle = st.session_state.last_result["handover_bundle"]
    with st.expander("📋 Your support reference", expanded=True):
        hm = st.session_state.pipeline.handover_manager
        st.code(hm.format_bundle_for_display(bundle), language=None)


# ── Quick chips (first message only) ─────────────────────────────────────────
if not st.session_state.messages:
    st.markdown('<div class="chips-label">Suggested topics</div>', unsafe_allow_html=True)
    chip_cols = st.columns(4)
    chips = [
        ("📦 Track order",       "Where is my order? I'd like to track it."),
        ("↩️ Start return",      "I want to start a return for my order."),
        ("💳 Request refund",    "I'd like to request a refund please."),
        ("❓ Order not arrived", "My order hasn't arrived yet."),
    ]
    for col, (label, message) in zip(chip_cols, chips):
        with col:
            if st.button(label, use_container_width=True, key=f"chip_{label}"):
                st.markdown(f"""
                <div class="msg-row user">
                    <div class="av usr">{c_init}</div>
                    <div><div class="bubble usr">{message}</div></div>
                </div>""", unsafe_allow_html=True)
                tp = st.empty()
                tp.markdown("""<div class="typing-wrap">
                    <div class="av bot">🤖</div>
                    <div class="typing-bubble">
                        <div class="td"></div><div class="td"></div><div class="td"></div>
                    </div></div>""", unsafe_allow_html=True)
                t0 = time.time()
                result = st.session_state.pipeline.process(message, customer_data=cdata)
                tp.empty()
                lat = (time.time() - t0) * 1000
                f = result.get("frustration", {})
                st.session_state.last_result = result
                st.session_state.latencies_ms.append(lat)
                st.session_state.frustration_history.append(f.get("frustration_score", 0))
                st.session_state.turn_labels.append(f"T{result.get('turn', 0)}")
                st.session_state.response_modes_used.append(result["response"]["mode"])
                st.session_state.messages.append({"role": "user", "text": message, "frustration": f.get("frustration_score", 0), "level": f.get("level", "calm")})
                st.session_state.messages.append({"role": "bot", "text": result["response"]["message"], "mode": result["response"]["mode"]})
                if result["response"].get("trigger_handover"):
                    st.session_state.show_survey = True
                st.rerun()


# ── Survey ────────────────────────────────────────────────────────────────────
if st.session_state.show_survey and not st.session_state.survey_submitted:
    st.markdown("""<div class="survey-shell">
        <div class="survey-hd">How did we do?</div>
        <div class="survey-sub">Takes 30 seconds — helps us improve.</div>
    </div>""", unsafe_allow_html=True)
    with st.form("survey"):
        c1, c2, c3 = st.columns(3)
        with c1: sat   = st.slider("Satisfaction", 1, 5, 3)
        with c2: emp   = st.slider("Empathy felt", 1, 5, 3)
        with c3: trust = st.slider("Trust", 1, 5, 3)
        resolved = st.radio("Issue resolved?", ["Yes, fully", "Partially", "No"], horizontal=True)
        comments = st.text_area("Comments (optional)")
        if st.form_submit_button("Submit →", use_container_width=True):
            st.session_state.survey_data = {
                "satisfaction": sat, "perceived_empathy": emp,
                "trust": trust, "resolved": resolved, "comments": comments
            }
            st.session_state.survey_submitted = True
            st.rerun()

if st.session_state.survey_submitted:
    d = st.session_state.survey_data
    st.markdown(f"""<div style="background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.2);
        border-radius:12px;padding:13px 17px;color:#4ade80;font-size:13px;margin:8px 0">
        ✅ Thank you! Satisfaction {d['satisfaction']}/5 · Empathy {d['perceived_empathy']}/5 · Trust {d['trust']}/5
    </div>""", unsafe_allow_html=True)


# ── Action buttons ────────────────────────────────────────────────────────────
if not st.session_state.pipeline.is_handed_over:
    b1, b2, _ = st.columns([1.2, 1.4, 3])
    with b1:
        if st.button("👤 Human Agent", use_container_width=True):
            result = st.session_state.pipeline.process("I want to speak to a human agent")
            f = result.get("frustration", {})
            st.session_state.last_result = result
            st.session_state.latencies_ms.append(0)
            st.session_state.frustration_history.append(f.get("frustration_score", 0.5))
            st.session_state.turn_labels.append(f"T{result.get('turn', 0)}")
            st.session_state.messages.append({"role": "user", "text": "I want to speak to a human agent", "frustration": 0.5})
            st.session_state.messages.append({"role": "bot", "text": result["response"]["message"], "mode": "handover"})
            st.session_state.show_survey = True
            st.rerun()
    with b2:
        if st.button("📋 Leave Feedback", use_container_width=True):
            st.session_state.show_survey = True
            st.rerun()


# ── Chat input ────────────────────────────────────────────────────────────────
user_input = st.chat_input(f"Message {BOT_NAME}...")
if user_input:
    hv_task = (
        f"PRIORITY VIP CUSTOMER: {c_name} spent £{c_spent:,.2f}. "
        f"Give elevated empathy and prioritise resolution."
    ) if is_vip else None

    st.markdown(f"""
    <div class="msg-row user">
        <div class="av usr">{c_init}</div>
        <div><div class="bubble usr">{user_input}</div></div>
    </div>""", unsafe_allow_html=True)

    import re as _re
    _order_match = (
        _re.search(r"order[\s\-#:]*(\d+)", user_input, _re.IGNORECASE) or
        _re.match(r"^#?(\d{4,})$", user_input.strip())
    )

    if _order_match:
        _onum = _order_match.group(1)
        st.markdown(f"""
        <div class="msg-row">
            <div class="av bot">🤖</div>
            <div><div class="bubble bot">Got it — checking on order {_onum} for you right now... 🔍</div></div>
        </div>""", unsafe_allow_html=True)

    tp = st.empty()
    tp.markdown("""<div class="typing-wrap">
        <div class="av bot">🤖</div>
        <div class="typing-bubble">
            <div class="td"></div><div class="td"></div><div class="td"></div>
        </div>
        <div style="font-size:11px;color:rgba(255,255,255,0.2);align-self:flex-end;margin-bottom:4px">
            Aria is typing...
        </div></div>""", unsafe_allow_html=True)

    t0 = time.time()
    result = st.session_state.pipeline.process(user_input, customer_data=cdata)
    tp.empty()
    lat = (time.time() - t0) * 1000

    f = result.get("frustration", {})
    mode = result["response"]["mode"]
    st.session_state.last_result = result
    st.session_state.latencies_ms.append(lat)
    st.session_state.frustration_history.append(f.get("frustration_score", 0))
    st.session_state.turn_labels.append(f"T{result.get('turn', 0)}")
    st.session_state.response_modes_used.append(mode)
    st.session_state.messages.append({"role": "user", "text": user_input, "frustration": f.get("frustration_score", 0), "level": f.get("level", "calm")})
    st.session_state.messages.append({"role": "bot", "text": result["response"]["message"], "mode": mode})
    if result["response"].get("trigger_handover"):
        st.session_state.show_survey = True
    st.rerun()