from pathlib import Path
import pandas as pd
import streamlit as st

st.title("Retail sales")
orders = pd.read_json(Path(__file__).with_name("orders.json"))
orders["net_cents"] = orders["gross_cents"] - orders["refund_cents"]
visible = orders
st.metric("Net revenue", f"{visible['net_cents'].sum() / 100:.2f}")
st.metric("Orders", str(len(visible)))
st.dataframe(visible, hide_index=True, alt="Orders matching the current category")
if visible.empty:
    st.info("No matching orders")
