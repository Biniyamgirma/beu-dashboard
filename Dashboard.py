import streamlit as st
st.set_page_config(page_title="beU Delivery Dashboard", layout="wide")

import os
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
import pandas as pd
import numpy as np
import datetime as dt

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')

with open(CONFIG_PATH) as file:
    config = yaml.load(file, Loader=SafeLoader)
    # print(config)
    # print("Cookie key value:", repr(config['cookie']['key']))

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
)
@st.cache_data
def load_data():
    np.random.seed(42)
    
    n_rows = 5000
    
    cities = ["Addis Ababa", "Bahir Dar", "Hawassa", "Mekelle", "Adama"]
    statuses = ["Delivered", "Pending", "Cancelled", "In Transit"]
    drivers = ["Abebe K.", "Kebede T.", "Sara M.", "Fatima A.", "Yonas B.", "Liya H."]
    
    df = pd.DataFrame({
        "Order ID": [f"ORD-{1000+i}" for i in range(n_rows)],
        "City": np.random.choice(cities, n_rows),
        "Status": np.random.choice(statuses, n_rows, p=[0.6, 0.15, 0.1, 0.15]),
        "Driver": np.random.choice(drivers, n_rows),
        "Date": pd.date_range(end=dt.datetime.today(), periods=n_rows).normalize(),
        "Amount": np.round(np.random.uniform(50, 1500, n_rows), 2),
        "Delivery Time (min)": np.random.randint(10, 90, n_rows),
    })
    
    return df
try:
    authenticator.login()
except Exception as e:
    st.error(e)

if st.session_state.get("authentication_status"):
    authenticator.logout("Logout", "sidebar")
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    category = st.sidebar.radio("Select Category:", ["ALL Delivered", "Call Center","Area Manager","Payment issues","Dashboard","Marketing","Customer Support"])
    if category == "ALL Delivered":
        st.subheader("ALL Delivered")
        df = load_data()
        # --- Date range picker ---
        min_date = df["Date"].min()
        max_date = df["Date"].max()

        st.title("beU Delivery Dashboard")
        date_range = st.date_input(
            "Select Date Range",
            value=(min_date, max_date),   # default: full range selected
            min_value=min_date,
            max_value=max_date,
        )
        

        
        # --- Filters ---
        col1, col2, col3,col4 = st.columns(4)

        with col1:
            city = st.selectbox("City", ["All"] + sorted(df["City"].unique().tolist()))

        with col2:
            status = st.selectbox("Status", ["All"] + sorted(df["Status"].unique().tolist()))

        with col3:
            driver = st.selectbox("Driver", ["All"] + sorted(df["Driver"].unique().tolist()))
        with col4:
            amount = st.selectbox("Amount", ["All"] + sorted(df["Amount"].unique().tolist()))

        filtered_df = df.copy()

        if city != "All":
            filtered_df = filtered_df[filtered_df["City"] == city]

        if status != "All":
            filtered_df = filtered_df[filtered_df["Status"] == status]

        if driver != "All":
            filtered_df = filtered_df[filtered_df["Driver"] == driver]
        if driver != "All":
            filtered_df = filtered_df[filtered_df["amount"] == amount]
        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = df[
                (df["Date"] >= pd.to_datetime(start_date)) &
                (df["Date"] <= pd.to_datetime(end_date))
            ]
        else:
            # user has only picked the start date so far — show everything until they finish
            filtered_df = df
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Orders", len(filtered_df))
        m2.metric("Total Revenue", f"{filtered_df['Amount'].sum():,.2f} ETB")
        m3.metric("Avg Delivery Time", f"{filtered_df['Delivery Time (min)'].mean():.1f} min" if len(filtered_df) else "N/A")
        # --- Display ---
        st.dataframe(filtered_df, use_container_width=True)

        # --- Quick metrics ---

    # ---- your real dashboard content goes here ----

elif st.session_state.get("authentication_status") is False:
    st.error("Username/password is incorrect")

elif st.session_state.get("authentication_status") is None:
    st.warning("Please enter your username and password")