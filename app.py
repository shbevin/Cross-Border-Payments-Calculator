import os
from dataclasses import dataclass
from typing import List, Dict, Optional
from decimal import Decimal, ROUND_HALF_UP

import streamlit as st

# ---------- Data models ----------
@dataclass
class Rail:
    name: str
    fixed_fee: float
    variable_fee_pct: float
    fx_spread_bps: int
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

# Shared rail presets
def rails_standard(
    agg_bps: int, card_bps: int, swift_bps: int,
    agg_fixed=1.99, agg_var=0.010, agg_eta=2,
    card_fixed=2.79, card_var=0.013, card_eta=4,
    swift_fixed=14.0, swift_var=0.002, swift_eta=24,
    min_send=10, max_send_agg=5000, max_send_card=3000, max_send_swift=50000
):
    return [
        Rail("Fintech Aggregator", agg_fixed, agg_var, agg_bps, agg_eta, min_send, max_send_agg),
        Rail("Card Network", card_fixed, card_var, card_bps, card_eta, min_send, max_send_card),
        Rail("SWIFT", swift_fixed, swift_var, swift_bps, swift_eta, 100, max_send_swift),
    ]

# ---------- Corridors: United States -> Americas ----------
CORRIDORS: List[Corridor] = [
    Corridor("United States", "Canada",   "USD", "CAD", rails_standard(70, 90, 30)),
    Corridor("United States", "Mexico",   "USD", "MXN", rails_standard(90, 120, 40)),

    Corridor("United States", "Guatemala","USD", "GTQ", rails_standard(120, 150, 55)),
    Corridor("United States", "Honduras", "USD", "HNL", rails_standard(140, 170, 60)),
    Corridor("United States", "El Salvador","USD","USD", rails_standard(0, 0, 0, swift_fixed=8.0)),
    Corridor("United States", "Nicaragua","USD", "NIO", rails_standard(150, 180, 65)),
    Corridor("United States", "Costa Rica","USD","CRC", rails_standard(120, 150, 50)),
    Corridor("United States", "Panama",   "USD", "USD", rails_standard(0, 0, 0, swift_fixed=8.0)),

    Corridor("United States", "Dominican Republic","USD","DOP", rails_standard(130, 160, 55)),
    Corridor("United States", "Jamaica", "USD", "JMD", rails_standard(140, 170, 60)),
    Corridor("United States", "Haiti",   "USD", "HTG", rails_standard(180, 220, 80)),
    Corridor("United States", "Trinidad & Tobago","USD","TTD", rails_standard(120, 150, 50)),

    Corridor("United States", "Colombia","USD", "COP", rails_standard(100, 130, 40)),
    Corridor("United States", "Peru",    "USD", "PEN", rails_standard(100, 130, 45)),
    Corridor("United States", "Chile",   "USD", "CLP", rails_standard(90,  120, 40)),
    Corridor("United States", "Argentina","USD","ARS", rails_standard(250, 300, 90, swift_eta=48, max_send_agg=3000, max_send_card=2000)),
    Corridor("United States", "Brazil",  "USD", "BRL", rails_standard(120, 140, 50)),
    Corridor("United States", "Uruguay", "USD", "UYU", rails_standard(110, 140, 45)),
    Corridor("United States", "Paraguay","USD", "PYG", rails_standard(140, 170, 60)),
    Corridor("United States", "Bolivia", "USD", "BOB", rails_standard(120, 150, 50)),
    Corridor("United States", "Ecuador", "USD", "USD", rails_standard(0, 0, 0, swift_fixed=8.0)),
]

# ---------- Mid-market FX rates ----------
MID_RATES = {
    ("USD", "CAD"): 1.30,
    ("USD", "MXN"): 19.50,
    ("USD", "GTQ"): 7.80,
    ("USD", "HNL"): 24.60,
    ("USD", "USD"): 1.00,
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
}

def mid_rate(src_ccy: str, dst_ccy: str) -> Optional[float]:
    return MID_RATES.get((src_ccy, dst_ccy))

# ---------- Helpers ----------
def fmt_money(x: float, ccy: str) -> str:
    q = Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    symbol = "$" if ccy == "USD" else ""
    return f"{symbol}{q} {ccy}"

def bps_to_pct(bps: int) -> float:
    return bps / 10000.0

def compute_quote(amount: float, rail: Rail, src_ccy: str, dst_ccy: str) -> Dict:
    variable_fee = amount * rail.variable_fee_pct
    fixed_fee = rail.fixed_fee
    total_fees_src = variable_fee + fixed_fee
    fx_principal = max(amount - total_fees_src, 0)
    base_rate = mid_rate(src_ccy, dst_ccy)
    spread_pct = bps_to_pct(rail.fx_spread_bps)

    if base_rate is None:
        customer_rate = None
        received_dst = None
        fx_spread_cost_src = 0.0
    else:
        if src_ccy == dst_ccy:
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

# ---------- UI ----------
st.set_page_config(page_title="Cross-Border Payment Fee Calculator", page_icon="💸", layout="centered")
st.title("💸 Cross-Border Payment Fee Calculator")
st.caption("Mock, for learning/demo purposes. Not financial advice. Rates are illustrative.")

srcs = sorted({c.src for c in CORRIDORS})
src_choice = st.selectbox("From (country)", srcs, index=0)
dsts = sorted({c.dst for c in CORRIDORS if c.src == src_choice})
if not dsts:
    st.warning("No destinations available for this source.")
    st.stop()

dst_choice = st.selectbox("To (country)", dsts)
corridor = next(c for c in CORRIDORS if c.src == src_choice and c.dst == dst_choice)
st.write(f"**Currency:** {corridor.currency_src} → {corridor.currency_dst}")

amount = st.number_input(f"Send amount ({corridor.currency_src})", min_value=10.0, step=10.0, value=1000.0)

# Manual validation (no Pydantic)
if amount <= 0:
    st.error("Amount must be greater than 0")
    st.stop()

rails = [r.name for r in corridor.rails]
rail_choice = st.selectbox("Payment rail", rails)
rail = next(r for r in corridor.rails if r.name == rail_choice)

limits = rail.send_limit_min, rail.send_limit_max
if amount < limits[0] or amount > limits[1]:
    st.warning(f"Typical limits for {rail.name}: {limits[0]:.0f}–{limits[1]:.0f} {corridor.currency_src}")

try:
    quote = compute_quote(amount, rail, corridor.currency_src, corridor.currency_dst)

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

    if quote["rate_mid"]:
        st.info(
            f"Mid-market rate: **{quote['rate_mid']:.4f}** | Customer rate: **{quote['rate_customer']:.4f}** "
            f"| Est. delivery: **~{quote['est_delivery_hours']}h**"
        )
    else:
        st.info(f"No FX conversion required | Est. delivery: **~{quote['est_delivery_hours']}h**")

    st.markdown("**Cost Breakdown (Source Currency)**")
    st.table({
        "Component": ["Fixed fee", "Variable fee", "FX spread cost (approx)"],
        "Amount": [
            fmt_money(quote["fixed_fee"], corridor.currency_src),
            fmt_money(quote["variable_fee"], corridor.currency_src),
            fmt_money(quote["fx_spread_cost_src"], corridor.currency_src),
        ],
    })

except Exception as e:
    st.error(str(e))
