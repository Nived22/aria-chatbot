# backend.py — Agent Backend Dashboard (agent/admin facing only)
# Run: streamlit run backend.py --server.port 8502
import streamlit as st
import json, os, glob, time, sys
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.logger import load_all_sessions
from aws.customer_db import list_all_customers

st.set_page_config(
    page_title="ShopSmart — Agent Dashboard",
    page_icon="🎧", layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&family=DM+Serif+Display&display=swap');

*, *::before, *::after { box-sizing: border-box; }
html, body, .stApp { background: #080810 !important; font-family: 'DM Sans', sans-serif !important; }
#MainMenu, footer, .stDeployButton { display: none !important; }
.block-container { padding: 24px 28px !important; max-width: 100% !important; }
[data-testid="stAppViewContainer"] { background: #080810 !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #0c0c18 !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
[data-testid="stSidebar"] > div:first-child { padding: 24px 18px !important; }

/* ── Page title ── */
.dash-title {
    font-family: 'DM Serif Display', serif;
    font-size: 26px; color: #fff;
    letter-spacing: -0.5px; margin-bottom: 2px;
}
.dash-sub { font-size: 13px; color: rgba(255,255,255,0.3); margin-bottom: 24px; }

/* ── Stat cards ── */
.stat-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 14px; margin-bottom: 24px; }
.stat-card {
    background: #0f0f1e;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 16px;
    padding: 18px 20px;
    position: relative; overflow: hidden;
}
.stat-card::before {
    content: '';
    position: absolute; top:0; left:0; right:0; height:3px;
    background: var(--accent, #6c63ff);
    border-radius: 16px 16px 0 0;
}
.stat-label { font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:1px; color:rgba(255,255,255,0.3); margin-bottom:8px; }
.stat-val { font-size:32px; font-weight:700; color:#fff; letter-spacing:-1px; line-height:1; }
.stat-sub { font-size:12px; color:rgba(255,255,255,0.3); margin-top:5px; }
.stat-badge {
    display:inline-block; padding:2px 8px; border-radius:10px;
    font-size:11px; font-weight:600; margin-top:6px;
}

/* ── Session cards ── */
.session-card {
    background: #0f0f1e;
    border: 1px solid rgba(255,255,255,0.07);
    border-left: 4px solid var(--left-color, #444);
    border-radius: 14px;
    padding: 16px 18px;
    margin-bottom: 10px;
    transition: transform 0.15s;
}
.session-card:hover { transform: translateX(3px); }
.sc-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
.sc-name { font-size:14px; font-weight:600; color:#fff; }
.sc-time { font-size:11px; color:rgba(255,255,255,0.3); }
.sc-meta { font-size:12px; color:rgba(255,255,255,0.45); display:flex; gap:16px; flex-wrap:wrap; }
.fchip {
    display:inline-flex; align-items:center; gap:4px;
    padding:3px 9px; border-radius:10px; font-size:12px; font-weight:600;
}
.f-calm     { background:rgba(34,197,94,0.12);  color:#4ade80; }
.f-mild     { background:rgba(234,179,8,0.12);  color:#facc15; }
.f-moderate { background:rgba(249,115,22,0.12); color:#fb923c; }
.f-high     { background:rgba(239,68,68,0.12);  color:#f87171; }
.f-critical { background:rgba(239,68,68,0.2);   color:#ef4444; }
.vip-dot {
    display:inline-block; width:8px; height:8px;
    background:#ffd700; border-radius:50%; margin-right:4px;
}

/* ── Customer table ── */
.cust-table { width:100%; border-collapse:separate; border-spacing:0 6px; }
.cust-table th {
    font-size:11px; font-weight:600; text-transform:uppercase;
    letter-spacing:1px; color:rgba(255,255,255,0.3);
    padding:8px 14px; text-align:left;
}
.cust-table td {
    background:#0f0f1e; color:rgba(255,255,255,0.75);
    padding:12px 14px; font-size:13px;
    border-top:1px solid rgba(255,255,255,0.05);
    border-bottom:1px solid rgba(255,255,255,0.05);
}
.cust-table td:first-child { border-radius:10px 0 0 10px; border-left:1px solid rgba(255,255,255,0.05); }
.cust-table td:last-child  { border-radius:0 10px 10px 0; border-right:1px solid rgba(255,255,255,0.05); }
.vip-pill-sm {
    background:rgba(255,215,0,0.12); border:1px solid rgba(255,215,0,0.25);
    color:#ffd700; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600;
}
.std-pill { background:rgba(255,255,255,0.05); color:rgba(255,255,255,0.4); padding:2px 8px; border-radius:10px; font-size:11px; }

/* ── Section headers ── */
.sec-hd {
    font-size:13px; font-weight:600; text-transform:uppercase;
    letter-spacing:1px; color:rgba(255,255,255,0.35);
    margin: 24px 0 12px; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:8px;
}

/* ── Status dot ── */
.live-dot {
    display:inline-block; width:8px; height:8px;
    background:#22c55e; border-radius:50%; margin-right:6px;
    animation: pulse-g 1.5s infinite;
}
@keyframes pulse-g{0%,100%{opacity:1}50%{opacity:0.3}}

/* ── Plotly charts ── */
.js-plotly-plot .plotly { background:transparent !important; }
.stPlotlyChart { border-radius:14px; overflow:hidden; }

hr { border-color:rgba(255,255,255,0.06) !important; }
.stMarkdown p { color:rgba(255,255,255,0.6) !important; font-size:13px !important; }
label, .stSelectbox label { color:rgba(255,255,255,0.45) !important; font-size:12px !important; }
[data-testid="stSelectbox"]>div>div {
    background:rgba(255,255,255,0.04) !important;
    border:1px solid rgba(255,255,255,0.1) !important;
    border-radius:10px !important; color:#e2e8f0 !important;
}
.stButton>button {
    background:linear-gradient(135deg,#6c63ff,#7c3aed) !important;
    color:#fff !important; border:none !important;
    border-radius:10px !important; font-family:'DM Sans',sans-serif !important;
    font-size:13px !important; font-weight:500 !important;
    box-shadow:0 4px 14px rgba(108,99,255,0.3) !important;
}
</style>
""", unsafe_allow_html=True)


LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


# ── Load session logs ─────────────────────────────────────────────────────────
def load_sessions(max_age_mins=60):
    """Load sessions from DynamoDB (deployed) or local files (local dev)."""
    raw_sessions = load_all_sessions(max_age_mins=max_age_mins)
    sessions = []
    for raw in raw_sessions:
        try:
            turns = raw.get("turns", [])
            frustration_history = [t.get("frustration_score", 0) for t in turns]
            latest_frustration  = frustration_history[-1] if frustration_history else 0
            turn_count          = len(turns)

            if latest_frustration < 0.25:   level = "calm"
            elif latest_frustration < 0.45: level = "mild"
            elif latest_frustration < 0.65: level = "moderate"
            elif latest_frustration < 0.78: level = "high"
            else:                           level = "critical"

            cdata         = raw.get("customer_data") or {}
            customer_name = cdata.get("name") or raw.get("customer_name", "Unknown Customer")
            customer_id   = cdata.get("customer_id") or raw.get("customer_id", "")
            is_vip        = cdata.get("is_vip") or raw.get("high_value_customer", False)

            sessions.append({
                "session_id":          raw.get("session_id", ""),
                "customer_name":       customer_name,
                "customer_id":         customer_id,
                "is_vip":              is_vip,
                "turn_count":          turn_count,
                "latest_frustration":  latest_frustration,
                "frustration_level":   level,
                "frustration_history": frustration_history,
                "handover_triggered":  raw.get("handover_triggered", False),
                "handover_reason":     raw.get("handover_reason"),
                "last_updated":        raw.get("last_updated", ""),
                "started_at":          raw.get("started_at", ""),
            })
        except Exception as e:
            print(f"[Backend] Error parsing session: {e}")
    return sorted(sessions, key=lambda s: s.get("last_updated",""), reverse=True)

def mock_sessions():
    """Return demo sessions when no real logs exist."""
    now = datetime.utcnow()
    return [
        {"session_id":"sess_001","customer_name":"James Wilson","customer_id":"C001",
         "is_vip":True,"turn_count":6,"latest_frustration":0.82,"frustration_level":"high",
         "frustration_history":[0.28,0.41,0.55,0.68,0.79,0.82],
         "handover_triggered":True,"handover_reason":"High frustration",
         "last_updated":(now-timedelta(minutes=3)).isoformat()},
        {"session_id":"sess_002","customer_name":"Sarah Chen","customer_id":"C002",
         "is_vip":False,"turn_count":3,"latest_frustration":0.38,"frustration_level":"mild",
         "frustration_history":[0.22,0.31,0.38],
         "handover_triggered":False,"handover_reason":None,
         "last_updated":(now-timedelta(minutes=8)).isoformat()},
        {"session_id":"sess_003","customer_name":"Mohammed Al-Hassan","customer_id":"C003",
         "is_vip":True,"turn_count":4,"latest_frustration":0.61,"frustration_level":"moderate",
         "frustration_history":[0.35,0.44,0.55,0.61],
         "handover_triggered":False,"handover_reason":None,
         "last_updated":(now-timedelta(minutes=1)).isoformat()},
        {"session_id":"sess_004","customer_name":"Emily Roberts","customer_id":"C004",
         "is_vip":False,"turn_count":2,"latest_frustration":0.18,"frustration_level":"calm",
         "frustration_history":[0.12,0.18],
         "handover_triggered":False,"handover_reason":None,
         "last_updated":(now-timedelta(minutes=15)).isoformat()},
    ]


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="margin-bottom:24px">
        <div style="font-family:'DM Serif Display',serif;font-size:20px;color:#fff;margin-bottom:2px">
            🎧 Agent Console
        </div>
        <div style="font-size:11px;color:rgba(255,255,255,0.3);text-transform:uppercase;letter-spacing:1px">
            ShopSmart Support
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:rgba(255,255,255,0.3);margin-bottom:8px">Navigation</div>', unsafe_allow_html=True)
    page = st.radio("", ["Live Sessions","Customer Database","Frustration Analytics","Handover Queue"],
                    label_visibility="collapsed")

    st.divider()
    st.markdown('<div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:rgba(255,255,255,0.3);margin-bottom:8px">Filters</div>', unsafe_allow_html=True)
    show_vip_only = st.toggle("VIP customers only", False)
    show_handover = st.toggle("Handover needed only", False)
    max_age = st.slider("Show sessions from last (min)", 5, 120, 60)

    st.divider()
    auto_refresh = st.toggle("Auto-refresh (30s)", True)
    if st.button("🔄 Refresh Now", use_container_width=True):
        st.rerun()

    st.markdown(f"""
    <div style="margin-top:16px;padding:12px;background:rgba(255,255,255,0.02);
                border-radius:10px;border:1px solid rgba(255,255,255,0.05);font-size:12px">
        <span class="live-dot"></span>
        <span style="color:#22c55e;font-weight:600">Live</span>
        <span style="color:rgba(255,255,255,0.3);margin-left:6px">
            {datetime.utcnow().strftime('%H:%M:%S')} UTC
        </span>
    </div>
    """, unsafe_allow_html=True)


# ── Load data ─────────────────────────────────────────────────────────────────
sessions = load_sessions(max_age)
if not sessions:
    sessions = mock_sessions()

if show_vip_only:
    sessions = [s for s in sessions if s.get("is_vip")]
if show_handover:
    sessions = [s for s in sessions if s.get("handover_triggered")]


def frust_class(score):
    if score < 0.25: return "calm","😌"
    if score < 0.45: return "mild","😐"
    if score < 0.65: return "moderate","😟"
    if score < 0.78: return "high","😤"
    return "critical","😡"

def left_color(score):
    if score < 0.25: return "#22c55e"
    if score < 0.45: return "#facc15"
    if score < 0.65: return "#fb923c"
    if score < 0.78: return "#f87171"
    return "#ef4444"


# ════════════════════════════════════════════════════════════════════════
# PAGE 1 — LIVE SESSIONS
# ════════════════════════════════════════════════════════════════════════
if page == "Live Sessions":
    st.markdown(f"""
    <div class="dash-title">Live Sessions</div>
    <div class="dash-sub"><span class="live-dot"></span>Monitoring {len(sessions)} active session{'s' if len(sessions)!=1 else ''}</div>
    """, unsafe_allow_html=True)

    # ── Stat cards ────────────────────────────────────────────────────────
    total  = len(sessions)
    high_f = sum(1 for s in sessions if s.get("latest_frustration",0) >= 0.65)
    handov = sum(1 for s in sessions if s.get("handover_triggered"))
    vip_ct = sum(1 for s in sessions if s.get("is_vip"))
    avg_f  = sum(s.get("latest_frustration",0) for s in sessions)/max(total,1)

    c1,c2,c3,c4 = st.columns(4)
    cards = [
        (c1,"Active Sessions",total,"","#6c63ff"),
        (c2,"High Frustration",high_f,f"{high_f/max(total,1)*100:.0f}% of sessions","#ef4444"),
        (c3,"Handovers",handov,"Awaiting agent","#f97316"),
        (c4,"VIP Customers",vip_ct,"Priority support","#ffd700"),
    ]
    for col, label, val, sub, accent in cards:
        with col:
            st.markdown(f"""
            <div class="stat-card" style="--accent:{accent}">
                <div class="stat-label">{label}</div>
                <div class="stat-val">{val}</div>
                <div class="stat-sub">{sub}</div>
            </div>""", unsafe_allow_html=True)

    # ── Session list ──────────────────────────────────────────────────────
    st.markdown('<div class="sec-hd">Active Sessions</div>', unsafe_allow_html=True)

    if not sessions:
        st.info("No active sessions in the selected time window.")
    else:
        for s in sessions:
            f_score = s.get("latest_frustration", 0)
            f_cls, f_icon = frust_class(f_score)
            lc = left_color(f_score)
            vip = s.get("is_vip", False)
            name = s.get("customer_name","Unknown")
            turns = s.get("turn_count",0)
            ho = s.get("handover_triggered", False)
            ts = s.get("last_updated","")
            try:
                dt = datetime.fromisoformat(ts)
                ago = int((datetime.utcnow()-dt).total_seconds()//60)
                time_str = f"{ago}m ago" if ago>0 else "just now"
            except: time_str = ""

            vip_html = '<span style="background:rgba(255,215,0,0.12);color:#ffd700;padding:2px 7px;border-radius:8px;font-size:11px;font-weight:600;margin-left:6px">⭐ VIP</span>' if vip else ""
            ho_html  = '<span style="background:rgba(239,68,68,0.12);color:#f87171;padding:2px 7px;border-radius:8px;font-size:11px;font-weight:600;margin-left:6px">🚨 Handover</span>' if ho else ""

            st.markdown(f"""
            <div class="session-card" style="--left-color:{lc}">
                <div class="sc-header">
                    <div>
                        <span class="sc-name">{name}</span>{vip_html}{ho_html}
                    </div>
                    <span class="sc-time">{time_str}</span>
                </div>
                <div class="sc-meta">
                    <span><span class="fchip f-{f_cls}">{f_icon} {f_score:.2f} — {f_cls}</span></span>
                    <span>💬 {turns} turns</span>
                    <span style="font-family:monospace;font-size:11px;color:rgba(255,255,255,0.2)">{s.get('session_id','')[:12]}...</span>
                </div>
            </div>""", unsafe_allow_html=True)

            # Inline frustration mini-chart
            hist = s.get("frustration_history",[])
            if hist and len(hist) > 1:
                with st.expander(f"📈 Frustration trend — {name}", expanded=ho):
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=list(range(1,len(hist)+1)), y=hist,
                        mode="lines+markers",
                        line=dict(color=lc, width=2.5),
                        marker=dict(size=7,color=lc),
                        fill="tozeroy", fillcolor=f"rgba({','.join(str(int(lc.lstrip('#')[i:i+2],16)) for i in (0,2,4))},0.1)"
                    ))
                    fig.add_hline(y=0.78,line_dash="dash",line_color="rgba(239,68,68,0.5)",
                                  annotation_text="Handover",annotation_font_size=10,
                                  annotation_font_color="rgba(239,68,68,0.7)")
                    fig.add_hline(y=0.50,line_dash="dot",line_color="rgba(249,115,22,0.4)",
                                  annotation_text="Alert",annotation_font_size=10,
                                  annotation_font_color="rgba(249,115,22,0.6)")
                    fig.update_layout(
                        height=160, margin=dict(t=8,b=8,l=8,r=8),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        xaxis=dict(title="Turn",gridcolor="rgba(255,255,255,0.04)",
                                   tickfont=dict(color="rgba(255,255,255,0.25)",size=9)),
                        yaxis=dict(range=[0,1],gridcolor="rgba(255,255,255,0.04)",
                                   tickfont=dict(color="rgba(255,255,255,0.25)",size=9)),
                        showlegend=False
                    )
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})


# ════════════════════════════════════════════════════════════════════════
# PAGE 2 — CUSTOMER DATABASE
# ════════════════════════════════════════════════════════════════════════
elif page == "Customer Database":
    st.markdown("""
    <div class="dash-title">Customer Database</div>
    <div class="dash-sub">Live data from AWS DynamoDB — priority customers flagged at £500+ spend</div>
    """, unsafe_allow_html=True)

    customers = list_all_customers()
    vip_count = sum(1 for c in customers if c.get("is_vip"))
    total_rev  = sum(c.get("total_spent",0) for c in customers)

    c1,c2,c3,c4 = st.columns(4)
    for col,(label,val,sub,acc) in zip([c1,c2,c3,c4],[
        ("Total Customers",len(customers),"In database","#6c63ff"),
        ("VIP Customers",vip_count,f"£500+ spend threshold","#ffd700"),
        ("Total Revenue",f"£{total_rev:,.0f}","Across all customers","#22c55e"),
        ("Avg Spend",f"£{total_rev/max(len(customers),1):,.0f}","Per customer","#a855f7"),
    ]):
        with col:
            st.markdown(f"""
            <div class="stat-card" style="--accent:{acc}">
                <div class="stat-label">{label}</div>
                <div class="stat-val">{val}</div>
                <div class="stat-sub">{sub}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown('<div class="sec-hd">All Customers</div>', unsafe_allow_html=True)

    # VIP progress bar chart
    df = pd.DataFrame(customers)
    df = df[df["customer_id"] != "C006"]  # exclude guest
    df = df.sort_values("total_spent", ascending=True)

    fig_bar = go.Figure()
    colors = ["#ffd700" if v else "#6c63ff" for v in df["is_vip"]]
    fig_bar.add_trace(go.Bar(
        x=df["total_spent"], y=df["name"],
        orientation="h",
        marker_color=colors,
        text=[f"£{v:,.0f}" for v in df["total_spent"]],
        textposition="outside",
        textfont=dict(color="rgba(255,255,255,0.6)",size=12)
    ))
    fig_bar.add_vline(x=500, line_dash="dash", line_color="rgba(255,215,0,0.5)",
                      annotation_text="VIP threshold £500",
                      annotation_font_color="rgba(255,215,0,0.7)",annotation_font_size=11)
    fig_bar.update_layout(
        height=280, margin=dict(t=8,b=8,l=8,r=60),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="rgba(255,255,255,0.05)",tickfont=dict(color="rgba(255,255,255,0.3)",size=10),
                   tickprefix="£"),
        yaxis=dict(tickfont=dict(color="rgba(255,255,255,0.6)",size=12)),
        showlegend=False
    )
    st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar":False})

    # Customer table
    rows = ""
    for c in sorted(customers, key=lambda x: x.get("total_spent",0), reverse=True):
        if c["customer_id"] == "C006": continue
        pill = '<span class="vip-pill-sm">⭐ VIP</span>' if c.get("is_vip") else '<span class="std-pill">Standard</span>'
        rows += f"""<tr>
            <td><strong style="color:#fff">{c['name']}</strong></td>
            <td style="font-family:monospace;font-size:12px;color:rgba(255,255,255,0.4)">{c['customer_id']}</td>
            <td>£{c.get('total_spent',0):,.2f}</td>
            <td>{c.get('order_count',0)}</td>
            <td>{pill}</td>
            <td style="color:rgba(255,255,255,0.4)">{c.get('last_order','—')}</td>
        </tr>"""

    st.markdown(f"""
    <table class="cust-table">
        <tr>
            <th>Name</th><th>ID</th><th>Total Spend</th>
            <th>Orders</th><th>Status</th><th>Last Order</th>
        </tr>
        {rows}
    </table>
    """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# PAGE 3 — FRUSTRATION ANALYTICS
# ════════════════════════════════════════════════════════════════════════
elif page == "Frustration Analytics":
    st.markdown("""
    <div class="dash-title">Frustration Analytics</div>
    <div class="dash-sub">Score distribution and trends across all active sessions</div>
    """, unsafe_allow_html=True)

    all_scores = [s.get("latest_frustration",0) for s in sessions]
    all_hist   = []
    for s in sessions:
        for i,sc in enumerate(s.get("frustration_history",[])):
            all_hist.append({"turn":i+1,"score":sc,"session":s.get("customer_name","?"),"is_vip":s.get("is_vip",False)})

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="sec-hd">Score Distribution</div>', unsafe_allow_html=True)
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=all_scores, nbinsx=10,
            marker_color="#6c63ff", marker_line_color="rgba(255,255,255,0.1)",
            marker_line_width=1, opacity=0.85
        ))
        fig_hist.add_vline(x=0.78,line_dash="dash",line_color="rgba(239,68,68,0.6)",
                           annotation_text="Handover",annotation_font_size=10)
        fig_hist.add_vline(x=0.50,line_dash="dot",line_color="rgba(249,115,22,0.5)",
                           annotation_text="Alert",annotation_font_size=10)
        fig_hist.update_layout(
            height=280,margin=dict(t=8,b=8,l=8,r=8),
            paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(title="Frustration Score",range=[0,1],
                       gridcolor="rgba(255,255,255,0.04)",
                       tickfont=dict(color="rgba(255,255,255,0.3)",size=10)),
            yaxis=dict(title="Sessions",gridcolor="rgba(255,255,255,0.04)",
                       tickfont=dict(color="rgba(255,255,255,0.3)",size=10)),
            showlegend=False
        )
        st.plotly_chart(fig_hist, use_container_width=True, config={"displayModeBar":False})

    with col2:
        st.markdown('<div class="sec-hd">Frustration Level Breakdown</div>', unsafe_allow_html=True)
        bands = {"Calm (0–0.25)":0,"Mild (0.25–0.45)":0,"Moderate (0.45–0.65)":0,
                 "High (0.65–0.78)":0,"Critical (0.78+)":0}
        for sc in all_scores:
            if sc < 0.25:   bands["Calm (0–0.25)"]        += 1
            elif sc < 0.45: bands["Mild (0.25–0.45)"]     += 1
            elif sc < 0.65: bands["Moderate (0.45–0.65)"] += 1
            elif sc < 0.78: bands["High (0.65–0.78)"]     += 1
            else:           bands["Critical (0.78+)"]     += 1

        fig_pie = go.Figure(go.Pie(
            labels=list(bands.keys()),
            values=list(bands.values()),
            hole=0.55,
            marker_colors=["#22c55e","#facc15","#fb923c","#f87171","#ef4444"],
            textfont=dict(size=12,color="#fff"),
        ))
        fig_pie.update_layout(
            height=280,margin=dict(t=8,b=8,l=8,r=8),
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(font=dict(color="rgba(255,255,255,0.5)",size=11),
                        bgcolor="rgba(0,0,0,0)"),
            showlegend=True
        )
        st.plotly_chart(fig_pie, use_container_width=True, config={"displayModeBar":False})

    # Frustration over turns — all sessions
    if all_hist:
        st.markdown('<div class="sec-hd">Frustration Progression — All Sessions</div>', unsafe_allow_html=True)
        fig_lines = go.Figure()
        for s in sessions:
            hist = s.get("frustration_history",[])
            if hist:
                color = "#ffd700" if s.get("is_vip") else "#6c63ff"
                fig_lines.add_trace(go.Scatter(
                    x=list(range(1,len(hist)+1)), y=hist,
                    mode="lines+markers",
                    name=s.get("customer_name","?"),
                    line=dict(color=color,width=2),
                    marker=dict(size=6)
                ))
        fig_lines.add_hline(y=0.78,line_dash="dash",line_color="rgba(239,68,68,0.4)")
        fig_lines.add_hline(y=0.50,line_dash="dot",line_color="rgba(249,115,22,0.3)")
        fig_lines.update_layout(
            height=300,margin=dict(t=8,b=8,l=8,r=8),
            paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(title="Turn",gridcolor="rgba(255,255,255,0.04)",
                       tickfont=dict(color="rgba(255,255,255,0.3)",size=10)),
            yaxis=dict(title="Frustration",range=[0,1],
                       gridcolor="rgba(255,255,255,0.04)",
                       tickfont=dict(color="rgba(255,255,255,0.3)",size=10)),
            legend=dict(font=dict(color="rgba(255,255,255,0.5)",size=11),
                        bgcolor="rgba(0,0,0,0)")
        )
        st.plotly_chart(fig_lines, use_container_width=True, config={"displayModeBar":False})

    # VIP vs Standard comparison
    vip_scores = [s.get("latest_frustration",0) for s in sessions if s.get("is_vip")]
    std_scores = [s.get("latest_frustration",0) for s in sessions if not s.get("is_vip")]
    if vip_scores or std_scores:
        st.markdown('<div class="sec-hd">VIP vs Standard — Average Frustration</div>', unsafe_allow_html=True)
        avg_vip = sum(vip_scores)/max(len(vip_scores),1)
        avg_std = sum(std_scores)/max(len(std_scores),1)
        fig_cmp = go.Figure()
        fig_cmp.add_trace(go.Bar(x=["VIP Customers","Standard Customers"],
                                  y=[avg_vip,avg_std],
                                  marker_color=["#ffd700","#6c63ff"],
                                  text=[f"{avg_vip:.2f}",f"{avg_std:.2f}"],
                                  textposition="outside",
                                  textfont=dict(color="rgba(255,255,255,0.7)",size=13)))
        fig_cmp.update_layout(
            height=220,margin=dict(t=24,b=8,l=8,r=8),
            paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(range=[0,1],gridcolor="rgba(255,255,255,0.04)",
                       tickfont=dict(color="rgba(255,255,255,0.3)",size=10)),
            xaxis=dict(tickfont=dict(color="rgba(255,255,255,0.6)",size=13)),
            showlegend=False
        )
        st.plotly_chart(fig_cmp, use_container_width=True, config={"displayModeBar":False})


# ════════════════════════════════════════════════════════════════════════
# PAGE 4 — HANDOVER QUEUE
# ════════════════════════════════════════════════════════════════════════
elif page == "Handover Queue":
    st.markdown("""
    <div class="dash-title">Handover Queue</div>
    <div class="dash-sub">Sessions requiring human agent intervention</div>
    """, unsafe_allow_html=True)

    handovers = [s for s in sessions if s.get("handover_triggered")]
    alerts    = [s for s in sessions if s.get("latest_frustration",0) >= 0.65
                 and not s.get("handover_triggered")]

    c1,c2 = st.columns(2)
    with c1:
        st.markdown(f"""
        <div class="stat-card" style="--accent:#ef4444">
            <div class="stat-label">Awaiting Agent</div>
            <div class="stat-val">{len(handovers)}</div>
            <div class="stat-sub">Need immediate attention</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="stat-card" style="--accent:#f97316">
            <div class="stat-label">At-Risk Sessions</div>
            <div class="stat-val">{len(alerts)}</div>
            <div class="stat-sub">Frustration ≥ 0.65 — monitor closely</div>
        </div>""", unsafe_allow_html=True)

    if handovers:
        st.markdown('<div class="sec-hd">🚨 Requires Agent — Handover Queue</div>', unsafe_allow_html=True)
        for s in handovers:
            f_score = s.get("latest_frustration",0)
            vip = s.get("is_vip",False)
            name = s.get("customer_name","Unknown")
            reason = s.get("handover_reason","High frustration")
            turns = s.get("turn_count",0)
            ts = s.get("last_updated","")
            try:
                dt = datetime.fromisoformat(ts)
                ago = int((datetime.utcnow()-dt).total_seconds()//60)
                time_str = f"{ago}m ago"
            except: time_str = ""

            vip_tag = "⭐ VIP · " if vip else ""
            st.markdown(f"""
            <div class="session-card" style="--left-color:#ef4444;background:rgba(239,68,68,0.05)!important">
                <div class="sc-header">
                    <div>
                        <span class="sc-name">🚨 {name}</span>
                        {'<span style="background:rgba(255,215,0,0.12);color:#ffd700;padding:2px 7px;border-radius:8px;font-size:11px;font-weight:600;margin-left:6px">⭐ VIP</span>' if vip else ''}
                    </div>
                    <span class="sc-time">{time_str}</span>
                </div>
                <div class="sc-meta">
                    <span><span class="fchip f-critical">😡 {f_score:.2f} — critical</span></span>
                    <span>💬 {turns} turns</span>
                    <span>📋 Reason: {reason}</span>
                    <span style="font-family:monospace;font-size:11px;color:rgba(255,255,255,0.2)">{s.get('session_id','')[:16]}</span>
                </div>
            </div>""", unsafe_allow_html=True)
    else:
        st.markdown('<div class="sec-hd">🚨 Handover Queue</div>', unsafe_allow_html=True)
        st.markdown('<p style="color:rgba(255,255,255,0.3);font-size:13px;padding:16px 0">No active handovers — all sessions handled by bot ✅</p>', unsafe_allow_html=True)

    if alerts:
        st.markdown('<div class="sec-hd">⚡ At-Risk — Monitor Closely</div>', unsafe_allow_html=True)
        for s in alerts:
            f_score = s.get("latest_frustration",0)
            f_cls, f_icon = frust_class(f_score)
            name = s.get("customer_name","Unknown")
            turns = s.get("turn_count",0)
            st.markdown(f"""
            <div class="session-card" style="--left-color:#f97316">
                <div class="sc-header">
                    <span class="sc-name">⚡ {name}</span>
                </div>
                <div class="sc-meta">
                    <span><span class="fchip f-{f_cls}">{f_icon} {f_score:.2f} — {f_cls}</span></span>
                    <span>💬 {turns} turns</span>
                    <span>Trending high — may require intervention</span>
                </div>
            </div>""", unsafe_allow_html=True)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(30)
    st.rerun()