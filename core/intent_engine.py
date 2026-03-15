# core/intent_engine.py
# Advanced LLM-powered response engine
# Improvements:
#   1. Better context memory — full conversation summary injected every turn
#   2. Personalised responses — customer name, spend, VIP status, order history baked in
#   3. Smarter intent detection — 12 intents detected locally before API call
#   4. Faster response time — Haiku for simple intents, Sonnet only for complex/high frustration

import os
import re
import random
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import anthropic
    _anthropic_available = True
except ImportError:
    _anthropic_available = False

try:
    from aws.order_db import lookup_order, format_order_for_claude
    _order_db_available = True
except ImportError:
    _order_db_available = False


# ── Intent definitions ────────────────────────────────────────────────────────
# Detected locally — no API call needed for classification
INTENTS = {
    "track_order": {
        "patterns": [r"where.*(my order|my parcel|my package)", r"track.*order",
                     r"order.*status", r"when.*arrive", r"when.*deliver",
                     r"wheres my", r"estimated.*delivery", r"delivery.*date"],
        "needs_order_number": True,
    },
    "return_item": {
        "patterns": [r"\breturn\b", r"send.*back", r"give.*back", r"return.*policy",
                     r"how.*return", r"want.*return"],
        "needs_order_number": True,
    },
    "refund_request": {
        "patterns": [r"\brefund\b", r"money back", r"reimburse", r"get.*paid back",
                     r"charge.*back", r"want.*money"],
        "needs_order_number": True,
    },
    "cancel_order": {
        "patterns": [r"\bcancel\b", r"cancel.*order", r"stop.*order", r"don.?t want"],
        "needs_order_number": True,
    },
    "wrong_item": {
        "patterns": [r"wrong (item|product|thing|size|colour|color)", r"not what i ordered",
                     r"sent.*wrong", r"incorrect.*item", r"different.*item"],
        "needs_order_number": True,
    },
    "damaged_item": {
        "patterns": [r"damaged", r"broken", r"arrived.*broken", r"smashed",
                     r"cracked", r"defective", r"not working", r"faulty"],
        "needs_order_number": True,
    },
    "missing_item": {
        "patterns": [r"missing (item|product|part)", r"didn.?t (receive|get|arrive)",
                     r"never (arrived|received|came)", r"not (arrived|received|delivered)",
                     r"order.*missing", r"hasn.?t arrived"],
        "needs_order_number": True,
    },
    "late_delivery": {
        "patterns": [r"late", r"delayed", r"taking.*long", r"should.*arrived",
                     r"expected.*\d+ (days?|weeks?)", r"overdue", r"weeks? wait"],
        "needs_order_number": True,
    },
    "change_address": {
        "patterns": [r"change.*address", r"update.*address", r"wrong.*address",
                     r"different.*address", r"new address"],
        "needs_order_number": True,
    },
    "payment_issue": {
        "patterns": [r"payment", r"charged (twice|double|wrong)", r"billing",
                     r"invoice", r"overcharged", r"wrong (amount|charge|price)"],
        "needs_order_number": False,
    },
    "account_help": {
        "patterns": [r"\baccount\b", r"\blogin\b", r"\bpassword\b", r"sign in",
                     r"can.?t (log|access|sign)", r"forgot.*password"],
        "needs_order_number": False,
    },
    "promo_discount": {
        "patterns": [r"discount", r"promo(tion)?", r"coupon", r"voucher",
                     r"code.*not work", r"offer", r"deal"],
        "needs_order_number": False,
    },
}

# Intent → human-readable context for Claude
INTENT_CONTEXT = {
    "track_order":    "The customer wants to track their order or know when it will arrive.",
    "return_item":    "The customer wants to return an item.",
    "refund_request": "The customer is requesting a refund.",
    "cancel_order":   "The customer wants to cancel their order.",
    "wrong_item":     "The customer received the wrong item.",
    "damaged_item":   "The customer received a damaged or defective item.",
    "missing_item":   "The customer's order or part of it never arrived.",
    "late_delivery":  "The customer's delivery is late or overdue.",
    "change_address": "The customer wants to change their delivery address.",
    "payment_issue":  "The customer has a billing or payment problem.",
    "account_help":   "The customer needs help with their account or login.",
    "promo_discount": "The customer has a query about a discount or promo code.",
}


# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """You are Aria, a customer support assistant for ShopSmart, an online store.

PERSONALITY:
- Warm, natural and human — never sound like a corporate script
- Never use stiff phrases like "I'd be happy to assist" or "Certainly!"
- Keep replies to 1–3 sentences — be concise and direct
- Always address what the customer actually said

TONE BY FRUSTRATION SCORE:
- 0.00–0.25 (calm):     Relaxed and friendly.
- 0.25–0.50 (mild):     Helpful and attentive. Acknowledge their situation briefly.
- 0.50–0.65 (moderate): Show empathy first — "I completely understand how frustrating that is."
- 0.65–0.78 (high):     Apologise genuinely and urgently. Take ownership. Show it matters.
- 0.78–1.00 (critical): Strong heartfelt apology. Validate them fully. Calm before escalate.

PERSONALISATION RULES:
- You will be given the customer's name — use it naturally once in the conversation, not every message
- You will be given their VIP status and spend — VIP customers get warmer, more attentive replies
- If their order history is provided — reference it naturally if relevant
- Never make up order details, tracking numbers, prices or dates

CONTEXT MEMORY RULES — CRITICAL:
- Read the FULL conversation summary and history BEFORE writing anything
- The context block at the top tells you exactly what has already happened
- If "ORDER NUMBER ALREADY PROVIDED" appears in context — you HAVE the order number. NEVER ask for it again under any circumstances.
- If the customer says "I already told you" or "I already mentioned" — apologise and acknowledge it immediately
- If the customer answered a question you asked — respond to their answer directly, do not repeat the question
- If the customer says "what's the update" or "any update" — they are following up. Check history and respond accordingly.
- NEVER ask for information the customer has already provided

INTENT HANDLING:
- track_order:    Give reassurance you're looking into it. Ask for order number if not given.
- return_item:    Explain returns are easy and you'll guide them through it.
- refund_request: Acknowledge the request, confirm you'll process it once you have the order number.
- cancel_order:   Act quickly — cancellations are time-sensitive.
- wrong_item:     Apologise, confirm the error, arrange replacement or refund.
- damaged_item:   Apologise sincerely, offer replacement or full refund immediately.
- missing_item:   Take it seriously — investigate immediately.
- late_delivery:  Acknowledge the wait, apologise, give a concrete next step.
- payment_issue:  Take billing issues seriously — reassure it will be resolved.
- account_help:   Guide them through account recovery calmly.
- promo_discount: Help them apply the code or escalate if it's a system issue.

Reply ONLY with the message to send. No preamble, no labels, no quotes."""


# ── Small talk — instant, no API ──────────────────────────────────────────────
_SMALL_TALK = [
    (r"^(hi+|hey+|hello+|howdy|hiya)[!.,]?\s*$",
     ["Hey! How can I help you today?", "Hi there! What can I do for you?",
      "Hello! What do you need help with?"]),
    (r"\bhow are you( doing)?\b",
     ["I'm doing well, thanks! How can I help?", "All good! What can I sort out for you?"]),
    (r"\bare you (a bot|an? ai|real|human)\b",
     ["I'm Aria, ShopSmart's virtual assistant! Pretty good at sorting things out — what do you need?",
      "I'm an AI assistant, yes! But I'm here to help. What's going on?"]),
    (r"\bwho are you\b|\bwhat are you\b",
     ["I'm Aria, your ShopSmart support assistant! How can I help?"]),
    (r"^(thanks?|thank you|cheers|ty)[!.,]?\s*$",
     ["No problem at all!", "Happy to help!", "Anytime!"]),
    (r"^(bye|goodbye|see you|cya)[!.,]?\s*$",
     ["Take care! Come back if you need anything.", "Bye! Hope everything gets sorted."]),
    (r"^(ok|okay|cool|alright|great|sounds good)[!.,]?\s*$",
     ["Great! Let me know if you need anything else.", "Perfect! Anything else I can help with?"]),
    (r"\byou('?re| are) (great|awesome|helpful|amazing)\b",
     ["Thanks, that's kind! Let me know if there's anything else."]),
    (r"\byou('?re| are) (useless|rubbish|terrible|stupid)\b",
     ["I'm sorry I haven't been helpful — let me try again. What do you need?"]),
]


# ── Order number detection — instant reply ────────────────────────────────────
def _check_order_number(message: str):
    """Returns (is_order, order_num) tuple."""
    msg = message.strip()
    match = re.search(r"order[\s\-#:]*(\d+)", msg, re.IGNORECASE)
    if match:
        return True, match.group(1)
    pure = re.match(r"^#?(\d{4,})$", msg.strip())
    if pure:
        return True, pure.group(1)
    return False, None


# ── Detect intent locally ─────────────────────────────────────────────────────
def detect_intent(message: str) -> str | None:
    msg = message.lower()
    for intent, cfg in INTENTS.items():
        for pattern in cfg["patterns"]:
            if re.search(pattern, msg):
                return intent
    return None


# ── Extract order number from history ────────────────────────────────────────
def _extract_order_from_history(history: list) -> str | None:
    """Scan conversation history for any order number already given."""
    for turn in reversed(history):
        text = turn.get("text","")
        match = re.search(r"order[\s\-#:]*(\d+)", text, re.IGNORECASE)
        if match:
            return match.group(1)
        pure = re.match(r"^#?(\d{4,})$", text.strip())
        if pure:
            return pure.group(1)
    return None


# ── Build conversation summary for memory ────────────────────────────────────
def _build_context_summary(history: list, customer_data: dict | None) -> str:
    """
    Builds a rich context block injected into every Claude call.
    This is what gives the bot its memory and personalisation.
    """
    lines = []

    # Customer profile — passed to Claude as internal context, never shown in chat
    if customer_data:
        name   = customer_data.get("name","Guest")
        spent  = customer_data.get("total_spent", 0)
        orders = customer_data.get("order_count", 0)
        is_vip = customer_data.get("is_vip", False)
        vip_str = "⭐ VIP CUSTOMER — give elevated empathy, use their name, prioritise resolution above all else" if is_vip else "Standard customer"
        lines.append(f"CUSTOMER PROFILE: {name} | Spend: £{spent:,.2f} | Orders: {orders} | {vip_str}")

    # Order number if already given — scan entire history
    known_order = _extract_order_from_history(history)
    if known_order:
        lines.append(
            f"⚠️ ORDER NUMBER ALREADY PROVIDED: #{known_order} — "
            f"NEVER ask for the order number again. You have it. "
            f"Any follow-up questions must reference order #{known_order} directly."
        )
        # Look up real order data for follow-up messages
        if _order_db_available:
            try:
                order = lookup_order(known_order)
                if order:
                    from aws.order_db import format_order_for_claude
                    lines.append(format_order_for_claude(order))
            except Exception:
                pass

    # Conversation summary — what has been discussed
    if history:
        topics = []
        for turn in history:
            intent = turn.get("intent")
            if intent and intent not in topics:
                topics.append(INTENT_CONTEXT.get(intent, intent))
        if topics:
            lines.append(f"TOPICS DISCUSSED: {' → '.join(topics)}")

        # Last thing bot asked (so it knows what customer is replying to)
        for turn in reversed(history):
            if turn.get("role") == "bot":
                last_bot = turn.get("text","")
                if "?" in last_bot:
                    lines.append(f"LAST QUESTION ASKED: \"{last_bot.strip()}\"")
                break

    return "\n".join(lines)


# ── Small talk check ──────────────────────────────────────────────────────────
def _check_small_talk(message: str) -> str | None:
    msg = message.strip()
    is_order, _ = _check_order_number(msg)
    if is_order: return None
    for pattern, replies in _SMALL_TALK:
        if re.search(pattern, msg, re.IGNORECASE):
            return random.choice(replies)
    return None


# ── Main entry point ──────────────────────────────────────────────────────────
def get_contextual_reply(
    message: str,
    frustration_score: float,
    conversation_history: list = None,
    customer_data: dict = None,
    intent: str = None,
) -> str | None:
    """
    Generate response using:
    1. Instant order number acknowledgement
    2. Instant small talk
    3. Claude API with full context memory + personalisation
       - Uses Haiku for calm/mild + simple intents (fast)
       - Uses Sonnet for high frustration or complex intents (quality)
    """
    # 1. Order number — detect in current message or history
    is_order, order_num = _check_order_number(message)

    # If not in current message, check history
    if not order_num and conversation_history:
        order_num = _extract_order_from_history(conversation_history)

    # Look up real order data from DynamoDB
    order_data = None
    if order_num and _order_db_available:
        try:
            order_data = lookup_order(order_num)
        except Exception as e:
            print(f"[IntentEngine] Order lookup error: {e}")

    # 2. Small talk — instant, no API
    small_talk = _check_small_talk(message)
    if small_talk:
        return small_talk

    # 3. Claude API
    api_key = os.getenv("ANTHROPIC_API_KEY","")
    if _anthropic_available and api_key and api_key not in ("","your_anthropic_api_key_here"):
        try:
            return _call_claude(
                message, frustration_score,
                conversation_history or [],
                customer_data or {},
                intent,
                order_num=order_num if is_order else None,
                order_data=order_data,
            )
        except Exception as e:
            import traceback
            print(f"[IntentEngine] ❌ Claude API error: {e}")
            print(f"[IntentEngine] Full error: {traceback.format_exc()}")
            print(f"[IntentEngine] Falling back to emergency fallback")

    # Emergency fallback — if order number given, never ask for it again
    if is_order and order_num:
        return f"Thanks, I have order {order_num}. I'm looking into this for you now — what's the issue you're experiencing?"

    return _emergency_fallback(message, frustration_score, conversation_history or [])


# ── Claude API call ───────────────────────────────────────────────────────────
def _call_claude(
    message: str,
    frustration_score: float,
    history: list,
    customer_data: dict,
    intent: str | None,
    order_num: str | None = None,
    order_data: dict | None = None,
) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # ── Model selection — fast vs quality ────────────────────────────────────
    # Haiku: calm/mild frustration + simple intents = fast response
    # Sonnet: high frustration or complex issue = best quality
    complex_intents = {"damaged_item","missing_item","refund_request","payment_issue","wrong_item"}
    use_sonnet = (
        frustration_score >= 0.65 or
        intent in complex_intents
    )
    model = "claude-sonnet-4-20250514" if use_sonnet else "claude-haiku-4-5-20251001"
    max_tokens = 180 if use_sonnet else 120

    # ── Tone instruction ──────────────────────────────────────────────────────
    if frustration_score >= 0.78:
        tone = (
            f"[FRUSTRATION: CRITICAL — {frustration_score:.2f}] "
            "CALM this customer first. Start with a strong heartfelt apology. "
            "Validate their frustration explicitly. Take personal ownership. "
            "Give one concrete action you are doing right now. "
            "Only mention human agent as an option at the end, not the first thing."
        )
    elif frustration_score >= 0.65:
        tone = (
            f"[FRUSTRATION: HIGH — {frustration_score:.2f}] "
            "Open with a genuine warm apology. Acknowledge specifically what frustrated them. "
            "Tell them this is being treated as a priority. Be human, not robotic."
        )
    elif frustration_score >= 0.50:
        tone = (
            f"[FRUSTRATION: MODERATE — {frustration_score:.2f}] "
            "Acknowledge their feelings first — 'I completely understand'. "
            "Then offer a clear proactive next step."
        )
    elif frustration_score >= 0.25:
        tone = (
            f"[FRUSTRATION: MILD — {frustration_score:.2f}] "
            "Be friendly, helpful and efficient. Get to the point."
        )
    else:
        tone = (
            f"[FRUSTRATION: CALM — {frustration_score:.2f}] "
            "Be warm, casual and conversational."
        )

    # ── Context block — memory + personalisation ──────────────────────────────
    context = _build_context_summary(history, customer_data)

    # ── Order data — real lookup from DynamoDB ───────────────────────────────
    order_ctx = ""
    if order_num and order_data:
        from aws.order_db import format_order_for_claude
        order_ctx = format_order_for_claude(order_data)
        order_ctx += (
            f"\n\nINSTRUCTION: You now have REAL order data above. "
            f"Use it to give a specific, accurate response. "
            f"DO NOT make up any details — use exactly what is shown. "
            f"DO NOT ask for the order number again."
        )
    elif order_num:
        order_ctx = (
            f"ORDER NUMBER PROVIDED: {order_num} — "
            f"Acknowledge you have it and tell them what you are doing next. "
            f"DO NOT ask for the order number again."
        )

    # ── Intent context ────────────────────────────────────────────────────────
    intent_ctx = ""
    if intent and intent in INTENT_CONTEXT:
        intent_ctx = f"DETECTED INTENT: {INTENT_CONTEXT[intent]}"

    # ── Build messages array ──────────────────────────────────────────────────
    messages = []

    # Last 10 turns of history (up from 8 — better memory)
    for turn in history[-10:]:
        role = "user" if turn.get("role") == "user" else "assistant"
        text = turn.get("text","").strip()
        if text:
            messages.append({"role": role, "content": text})

    # Deduplicate consecutive same-role messages
    cleaned = []
    for msg in messages:
        if cleaned and cleaned[-1]["role"] == msg["role"]:
            cleaned[-1]["content"] += " " + msg["content"]
        else:
            cleaned.append(dict(msg))
    messages = cleaned

    # Current message — inject tone + context + intent
    # hv_task is passed via customer_data — NEVER exposed to customer
    parts = [p for p in [context, order_ctx, intent_ctx, tone, f"Customer message: {message}"] if p]
    messages.append({"role":"user","content":"\n\n".join(parts)})
    # Note: customer_data VIP info is already in context block above — not shown in chat

    # Claude requires first message to be from user
    if not messages or messages[0]["role"] != "user":
        messages = [{"role":"user","content":"\n\n".join(parts)}]

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=_SYSTEM_PROMPT,
        messages=messages
    )

    reply = response.content[0].text.strip().strip('"').strip("'")
    print(f"[IntentEngine] Model: {model} | Intent: {intent} | Frustration: {frustration_score:.2f}")
    return reply if reply else None


# ── Emergency fallback ────────────────────────────────────────────────────────
def _emergency_fallback(message: str, frustration_score: float, history: list = None) -> str | None:
    """Fallback used only when Claude API is unavailable. History-aware."""
    msg = message.lower()
    history = history or []

    # Check if order number was already given in history
    known_order = _extract_order_from_history(history)

    if frustration_score >= 0.78:
        return "I'm truly sorry you're experiencing this. Let me connect you with a team member who can resolve this immediately."
    elif frustration_score >= 0.50:
        if known_order:
            return f"I understand, and I'm sorry about that. I'm looking into order {known_order} for you right now."
        return "I'm sorry to hear that. Could you share your order number so I can look into this right away?"
    elif any(w in msg for w in ["late","delayed","missing","track","where","update","status"]):
        if known_order:
            return f"I'm on it — checking the latest status on order {known_order} for you now."
        return "Could you share your order number so I can track that for you?"
    elif any(w in msg for w in ["order","refund","return","delivery","cancel","damaged","wrong"]):
        if known_order:
            return f"Got it, I have order {known_order} here. What would you like to do — return, refund or something else?"
        return "Happy to help! Could you share your order number so I can look into it?"
    elif any(w in msg for w in ["account","login","password","sign"]):
        return "I can help with your account. What issue are you running into?"
    elif len(message.split()) <= 2:
        if known_order:
            return f"Sure — what would you like me to do with order {known_order}?"
        return "Could you tell me a bit more about what you need help with?"
    return None