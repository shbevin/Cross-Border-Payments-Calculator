import os
from dataclasses import dataclass
from typing import List, Dict, Optional
from decimal import Decimal, ROUND_HALF_UP

import streamlit as st
from pydantic import BaseModel, Field, validator

# Optional AI explainer
USE_AI = bool(os.getenv("OPENAI_API_KEY"))
if USE_AI:
    try:
        from openai import OpenAI
        client = OpenAI()
    except Exception:
        USE_AI = False

# ---------- Mock Data (realistic but simplified) ----------
@dataclass
class Rail:
    name: str
    fixed_fee: float         # USD (or source currency)
    variable_fee_pct: float  # e.g., 0.9 for 0.9%
    fx_spread_bps: int       # basis points on mid-market (e.g., 150 = 1.5%)
    est_delivery_hours: int
    send_limit_min: float
    send_limit_max: float

@dataclass
class Corridor:
    src: str
    dst: str
    currency_src: str
    currency_dst: str
    rails: List[Rail]

# Shared rail presets (tune per corridor if you like)
def rails_standard(agg_bps: int, card_bps: int, swift_bps: int,
                   agg_fixed=1.99, agg_var=0.010, agg_eta=2,
                   card_fixed=2.79, card_var=0.013, card_eta=4,
                   swift_fixed=14.0, swift_var=0.002, swift_eta=24,
                   min_send=10, max_send_agg=5000, max_send_card=3000, max_send_swift=50000):
    return [
        Rail("Fintech Aggregator", fixed_fee=agg_fixed, variable_fee_pct=agg_var, fx_spread_bps=agg_bps, est_delivery_hours=agg_eta, send_limit_min=min_send,  send_limit_max=max_send_agg),
        Rail("Card Network",       fixed_fee=card_fixed, variable_fee_pct=card_var, fx_spread_bps=card_bps, est_delivery_hours=card_eta, send_limit_min=min_send,  send_limit_max=max_send_card),
        Rail("SWIFT",              fixed_fee=swift_fixed, variable_fee_pct=swift_var, fx_spread_bps=swift_bps, est_delivery_hours=swift_eta, send_limit_min=100, send_limit_max=max_send_swift),
    ]

# Americas-only corridors (United States → destination)
CORRIDORS: List[Corridor] = [
    # North America
    Corridor("United States", "Canada",   "USD", "CAD", rails_standard(agg_bps=70,  card_bps=90,  swift_bps=30)),
    Corridor("United States", "Mexico",   "USD", "MXN", rails_standard(agg_bps=90,  card_bps=120, swift_bps=40)),

    # Central America
    Corridor("United States", "Guatemala","USD", "GTQ", rails_standard(agg_bps=120, card_bps=150, swift_bps=55)),
    Corridor("United States", "Honduras", "USD", "HNL", rails_standard(agg_bps=140, card_bps=170, swift_bps=60)),
    Corridor("United States", "El Salvador","USD","USD", rails_standard(agg_bps=0,  card_bps=0,   swift_bps=0, swift_fixed=8.0)),  # Dollarized
    Corridor("United States", "Nicaragua","USD", "NIO", rails_standard(agg_bps=150, card_bps=180, swift_bps=65)),
    Corridor("United States", "Costa Rica","USD","CRC", rails_standard(agg_bps=120, card_bps=150, swift_bps=50)),
    Corridor("United States", "Panama",   "USD", "USD", rails_standard(agg_bps=0,  card_bps=0,   swift_bps=0, swift_fixed=8.0)),  # Dollarized

    # Caribbean
    Corridor("United States", "Dominican Republic","USD","DOP", rails_standard(agg_bps=130, card_bps=160, swift_bps=55)),
    Corridor("United States", "Jamaica", "USD", "JMD", rails_standard(agg_bps=140, card_bps=170, swift_bps=60)),
    Corridor("United States", "Haiti",   "USD", "HTG", rails_standard(agg_bps=180, card_bps=220, swift_bps=80)),
    Corridor("United States", "Trinidad & Tobago","USD","TTD", rails_standard(agg_bps=120, card_bps=150, swift_bps=50)),

    # South America (Andean + Southern Cone + Brazil)
    Corridor("United States", "Colombia","USD", "COP", rails_standard(agg_bps=100, card_bps=130, swift_bps=40)),
    Corridor("United States", "Peru",    "USD", "PEN", rails_standard(agg_bps=100, card_bps=130, swift_bps=45)),
    Corridor("United States", "Chile",   "USD", "CLP", rails_standard(agg_bps=90,  card_bps=120, swift_bps=40)),
    Corridor("United States", "Argentina","USD","ARS", rails_standard(agg_bps=250, card_bps=300, swift_bps=90, swift_eta=48, max_send_agg=3000, max_send_card=2000)),
    Corridor("United States", "Brazil",  "USD", "BRL", rails_standard(agg_bps=120, card_bps=140, swift_bps=50)),
    Corridor("United States", "Uruguay", "USD", "UYU", rails_standard(agg_bps=110, card_bps=140, swift_bps=45)),
    Corridor("United States", "Paraguay","USD", "PYG", rails_standard(agg_bps=140, card_bps=170, swift_bps=60)),
    Corridor("United States", "Bolivia", "USD", "BOB", rails_standard(agg_bps=120, card_bps=150, swift_bps=50)),
    Corridor("United States", "Ecuador", "USD", "USD", rails_standard(agg_bps=0,   card_bps=0,   swift_bps=0, swift_fixed=8.0)),  # Dollarized
    # (Optional) Venezuela: volatile; keep spreads high if included
    # Corridor("United States", "Venezuela","USD","VES", rails_standard(agg_bps=400, card_bps=500, swift_bps=150, swift_eta=48)),
]

# Pretend mid-market FX; illustrative only (USD → local)
MID_RATES = {
    ("USD", "CAD"): 1.30,
    ("USD", "MXN"): 19.50,

    ("USD", "GTQ"): 7.80,
    ("USD", "HNL"): 24.60,
    ("USD", "USD"): 1.00,  # Dollarized (El Salvador, Panama, Ecuador)
    ("USD", "NIO"): 36.70,
    ("USD", "CRC"): 515.00,

    ("USD", "DOP"): 59.00,
    ("USD", "JMD"): 156.00,
    ("USD", "HTG"): 132.00,
    ("USD", "TTD"): 6.80,

    ("USD", "COP"): 4150.00,
    ("USD", "PEN"): 3.70,
    ("USD", "CLP"): 910.00,
    ("USD", "ARS"): 950.00,
    ("USD", "BRL"): 5.10,
    ("USD", "UYU"): 39.00,
    ("USD", "PYG"): 7400.00,
    ("USD", "BOB"): 6.90,
    # ("USD", "VES"): 40.00,  # if Venezuela enabled
}
def mid_rate(src_ccy: str, dst_ccy: str) -> Optional[float]:
    return MID_RATES.get((src_ccy, dst_ccy))

# ---------- Validation ----------
class InputModel(BaseModel):
    amount: float = Field(gt=0, description="Amount to send in source currency")

    @validator("amount")
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError("Amount must be > 0")
        return v

# ---------- Helpers ----------
def fmt_money(x: float, ccy: str) -> str:
    q = Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    symbol = "$" if ccy == "USD" else ""
    return f"{symbol}{q} {ccy}"

def bps_to_pct(bps: int) -> float:
    return bps / 10000.0

def compute_quote(amount: float, rail: Rail, src_ccy: str, dst_ccy: str) -> Dict:
    # Fees
    variable_fee = amount * rail.variable_fee_pct
    fixed_fee = rail.fixed_fee
    total_fees_src = variable_fee + fixed_fee

    # Amount that goes into FX after deducting fees
    fx_principal = max(amount - total_fees_src, 0)

    # FX
    base_rate = mid_rate(src_ccy, dst_ccy)
    spread_pct = bps_to_pct(rail.fx_spread_bps)

    if base_rate is None:
        customer_rate = None
        received_dst = None
        fx_spread_cost_src = 0.0
    else:
        if src_ccy == dst_ccy:
            # No FX conversion for same currency (e.g., USD→USD)
            customer_rate = base_rate
            fx_spread_cost_src = 0.0
        else:
            customer_rate = base_rate * (1 - spread_pct)
            fx_spread_cost_src = fx_principal * (base_rate - customer_rate)

        received_dst = fx_principal * customer_rate

    return {
        "rail": rail.name,
        "fixed_fee": fixed_fee,
        "variable_fee": variable_fee,
        "total_fees_src": total_fees_src,
        "fx_spread_bps": rail.fx_spread_bps,
        "fx_spread_cost_src": fx_spread_cost_src if base_rate else 0.0,
        "rate_mid": base_rate if base_rate else 0.0,
        "rate_customer": customer_rate if base_rate else 0.0,
        "fx_principal": fx_principal,
        "received_dst": received_dst if base_rate else None,
        "est_delivery_hours": rail.est_delivery_hours,
        "limits": (rail.send_limit_min, rail.send_limit_max),
    }

def ai_explain(corridor: Corridor, rail_quote: Dict, amount: float) -> str:
    if not USE_AI:
        # Fallback non-AI explainer
        return (
            f"Money moves via **{rail_quote['rail']}**. We deduct fixed (${rail_quote['fixed_fee']:.2f}) "
            f"+ variable ({rail_quote['variable_fee']:.2f}) fees, convert the remaining amount at the "
            f"customer rate ({rail_quote['rate_customer']:.4f} vs mid {rail_quote['rate_mid']:.4f}), "
            f"and deliver in ~{rail_quote['est_delivery_hours']} hours. FX spread of "
            f"{rail_quote['fx_spread_bps']} bps covers liquidity, compliance, and operations."
        )
    # With OpenAI
    sys = (
        "You are a payments product expert. Explain cross-border flow simply, in 3–5 sentences, "
        "avoiding hype. Include why the FX spread exists and what affects delivery time."
    )
    user = (
        f"Corridor: {corridor.src} ({corridor.currency_src}) → {corridor.dst} ({corridor.currency_dst}). "
        f"Rail: {rail_quote['rail']}. Amount: {amount} {corridor.currency_src}. "
        f"Fees: fixed {rail_quote['fixed_fee']:.2f}, variable {rail_quote['variable_fee']:.2f}. "
        f"Mid rate {rail_quote['rate_mid']:.4f}, customer rate {rail_quote['rate_customer']:.4f}. "
        f"FX spread {rail_quote['fx_spread_bps']} bps. ETA {rail_quote['est_delivery_hours']} hours."
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":sys},{"role":"user","content":user}],
            temperature=0.2,
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return "Explanation unavailable right now."

# ---------- UI ----------
st.set_page_config(page_title="Cross-Border Payment Fee Calculator", page_icon="💸", layout="centered")

st.title("💸 Cross-Border Payment Fee Calculator")
st.caption("Mock, for learning/demo purposes. Not financial advice. Rates are illustrative.")

# Corridor pickers
srcs = sorted({c.src for c in CORRIDORS})
src_choice = st.selectbox("From (country)", srcs, index=srcs.index("United States") if "United States" in srcs else 0)
dsts = sorted({c.dst for c in CORRIDORS if c.src == src_choice})
dst_choice = st.selectbox("To (country)", dsts)

corridor = next(c for c in CORRIDORS if c.src == src_choice and c.dst == dst_choice)
st.write(f"**Currency:** {corridor.currency_src} → {corridor.currency_dst}")

amount = st.number_input(f"Send amount ({corridor.currency_src})", min_value=10.0, step=10.0, value=1000.0)
rails = [r.name for r in corridor.rails]
rail_choice = st.selectbox("Payment rail", rails)

rail = next(r for r in corridor.rails if r.name == rail_choice)
limits = rail.send_limit_min, rail.send_limit_max
if amount < limits[0] or amount > limits[1]:
    st.warning(f"Typical limits for {rail.name}: {limits[0]:.0f}–{limits[1]:.0f} {corridor.currency_src}")

# Compute
try:
    InputModel(amount=amount)
    quote = compute_quote(amount, rail, corridor.currency_src, corridor.currency_dst)

    # Summary
    st.subheader("Quote")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Fixed fee", fmt_money(quote["fixed_fee"], corridor.currency_src))
        st.metric("Variable fee", fmt_money(quote["variable_fee"], corridor.currency_src))
        st.metric("FX spread (bps)", f"{quote['fx_spread_bps']} bps")
    with col2:
        st.metric("Total fees", fmt_money(quote["total_fees_src"], corridor.currency_src))
        st.metric("FX principal", fmt_money(quote["fx_principal"], corridor.currency_src))
        if quote["received_dst"] is not None:
            st.metric("Recipient receives", fmt_money(quote["received_dst"], corridor.currency_dst))

    # Rates + ETA
    if quote["rate_mid"]:
        st.info(
            f"Mid-market rate: **{quote['rate_mid']:.4f}** | Customer rate: **{quote['rate_customer']:.4f}** "
            f"| Est. delivery: **~{quote['est_delivery_hours']}h**"
        )
    else:
        st.info(f"No FX conversion required | Est. delivery: **~{quote['est_delivery_hours']}h**")

    # Breakdown table
    st.markdown("**Cost Breakdown (Source Currency)**")
    st.table({
        "Component": ["Fixed fee", "Variable fee", "FX spread cost (approx)"],
        "Amount": [
            fmt_money(quote["fixed_fee"], corridor.currency_src),
            fmt_money(quote["variable_fee"], corridor.currency_src),
            fmt_money(quote["fx_spread_cost_src"], corridor.currency_src),
        ],
    })

    # Explainer
    st.markdown("### How the money moves")
    st.write(ai_explain(corridor, quote, amount))

    st.caption("Note: This is a simplified model for learning/demo. Real quotes vary by KYC, corridor liquidity, scheme rules, and partner contracts.")
except Exception as e:
    st.error(str(e))
