import streamlit as st
st.set_page_config(page_title="beU Delivery Dashboard", layout="wide")

import os
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
import pandas as pd 
import numpy as np
import datetime as dt
import plotly.figure_factory as ff

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')
from data_fetcher import (
    fetch_data_all_delivered
)



with open(CONFIG_PATH) as file:
    config = yaml.load(file, Loader=SafeLoader)

from numpy.random import default_rng as rng
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
)


RESTAURANT_NAMES = [
    "818 Burger |Bole", "818 Burgers", "Chanoly Noodles | S...",
    "Smash Burger |Bole", "Akwaba Burger|Sum...", "Pullup Burger",
    "OSCAR BURGER|Bal...", "Rivonia Eatery | Sum...",
    "Chao Fan Fried Rice", "Choke Burger | Lebu", "Simple Bistro |Sum...",
]

BD_NAMES = [
    "Yeabtsega", "Chernet", "Yohannes", "Abel Wako", "Harege",
]


@st.cache_data
def restaurant_bd_map():
    """Fixed Restaurant name -> BD NAME lookup (deterministic seed)."""
    rng = np.random.default_rng(7)
    bd_for_restaurant = rng.choice(BD_NAMES, len(RESTAURANT_NAMES))
    return dict(zip(RESTAURANT_NAMES, bd_for_restaurant))


@st.cache_data
def load_data():
    result_df = fetch_data_all_delivered()
    if not result_df.empty:
        df = pd.DataFrame({
            "Order ID": result_df['ORDERS'],
            "Restaurant name": result_df['Restaurant name'],
            "created_at":result_df['created_at'],
            "coupon_discount_amount": result_df['coupon_discount_amount'],
            "restaurant_discount": result_df['restaurant_discount'],
            "restaurant_discount_on_food": result_df['restaurant_discount_on_food'],
            "beu_discount": result_df['beu_discount'],
            "beu_discount_on_food": result_df['beu_discount_on_food'],
            "restaurant_fee": result_df['restaurant_fee'],
            "commission_value": result_df['commission_value'],
            "categories_name": result_df['Categories_Name'],
            "team": result_df['Team'],
        })
    return df



@st.cache_data
def load_restaurant_data(seed=42):
    
    rng = np.random.default_rng(seed)

    df = pd.DataFrame({
        "Restaurant name": RESTAURANT_NAMES,
        "BD NAME": rng.choice(BD_NAMES, len(RESTAURANT_NAMES)),
        "commission_value": rng.integers(5_000, 60_000, len(RESTAURANT_NAMES)),
        "ORDERS": rng.integers(20, 400, len(RESTAURANT_NAMES)),
    })
    return df


def fetch_restaurant_data_live():
    
    seed = np.random.randint(0, 1_000_000)
    return load_restaurant_data.__wrapped__(seed=seed)


def show_bar_table(df, group_col, value_col, title, show_rank=True):
    
    st.subheader(title)

    if df.empty:
        st.info("No data for the current filter selection.")
        return

    agg = (
        df.groupby(group_col, as_index=False)[value_col]
        .sum()
        .sort_values(value_col, ascending=False)
        .reset_index(drop=True)
    )

    if show_rank:
        agg.index = agg.index + 1  # 1-based rank, like the reference image

    st.dataframe(
        agg,
        width='stretch',
        hide_index=not show_rank,
        column_config={
            group_col: st.column_config.TextColumn(group_col),
            value_col: st.column_config.ProgressColumn(
                value_col,
                format="%.0f",
                min_value=0,
                max_value=float(agg[value_col].max()),
            ),
        },
    )


try:
    authenticator.login()
except Exception as e:
    st.error(e)

if st.session_state.get("authentication_status"):
    authenticator.logout("Logout", "sidebar")
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    category = st.sidebar.radio(
        "Select Category:",
        ["ALL Delivered", "Restaurant BD Performance", "Call Center", "Area Manager",
         "Payment issues", "Dashboard", "Marketing", "Customer Support"]
    )

    if category == "ALL Delivered":
        st.subheader("ALL Delivered")
        df = load_data()

        # --- Date range picker ---
        min_date = df["Date"].min()
        max_date = df["Date"].max()

        st.title("beU Delivery Dashboard")
        date_range = st.date_input(
            "Select Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        # --- Filters ---
        col1, col2, col3, col4 = st.columns(4)

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

        if amount != "All":
            filtered_df = filtered_df[filtered_df["Amount"] == amount]

        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = filtered_df[
                (filtered_df["Date"] >= pd.to_datetime(start_date)) &
                (filtered_df["Date"] <= pd.to_datetime(end_date))
            ]
        # if the user has only picked the start date so far, keep showing
        # whatever the other filters already produced (no reset to full df)

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Orders", len(filtered_df))
        m2.metric("Total Revenue", f"{filtered_df['Amount'].sum():,.2f} ETB")
        m3.metric("Restaurant fee", f"2200000")

        m1.metric("Restaurant Discount", '3000')
        m2.metric("Restaurant Discount On Food", "40000")
        m3.metric("Commission Value", f"2200000")

        m1.metric("beu Discount", '3000')
        m2.metric("beu Discount On Food", "40000")
        m3.metric("Coupon Discount Amount", f"2200000")

        
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            show_bar_table(
                filtered_df,
                group_col="BD NAME",
                value_col="commission_value",
                title="BD Performance — Commission Value",
                show_rank=True,
            )

        with chart_col2:
            show_bar_table(
                filtered_df,
                group_col="Restaurant name",
                value_col="beu_discount_on_food",
                title="Restaurant — beU Discount On Food",
                show_rank=False,
            )

        st.title("Restaurant BD Performance")

        update_online = st.checkbox(
            "Update graph online",
            help="Tick this to pull fresh data instead of the cached snapshot."
        )
        if update_online:
            rest_df = fetch_restaurant_data_live()
            st.caption("Showing live data (refreshes each time you reload).")
        else:
            rest_df = load_restaurant_data()
            st.caption("Showing cached data.")

        st.dataframe(
            rest_df,
            width='stretch',
            hide_index=True,
            column_config={
                "Restaurant name": st.column_config.TextColumn("Restaurant name"),
                "BD NAME": st.column_config.TextColumn("BD NAME"),
                "commission_value": st.column_config.ProgressColumn(
                    "commission_value",
                    format="%d",
                    min_value=0,
                    max_value=int(rest_df["commission_value"].max()),
                ),
                "ORDERS": st.column_config.ProgressColumn(
                    "ORDERS",
                    format="%d",
                    min_value=0,
                    max_value=int(rest_df["ORDERS"].max()),
                ),
            },
        )

        if update_online:
            if st.button("Refresh now"):
                st.cache_data.clear()
                st.rerun()

      
        show_bar_table(
            filtered_df,
            group_col="BD NAME",
            value_col="commission_value",
            title="BD Performance — Commission Value",
            show_rank=True,
        )

        hist_data = [
            rng(0).standard_normal(200) - 2,
            rng(1).standard_normal(200),
            rng(2).standard_normal(200) + 2,
        ]
        group_labels = ["Group 1", "Group 2", "Group 3"]

        fig = ff.create_distplot(
            hist_data, group_labels, bin_size=[0.1, 0.25, 0.5]
        )

        st.plotly_chart(fig)
    # ---- your other categories (Call Center, Area Manager, etc.) go here ----

elif st.session_state.get("authentication_status") is False:
    st.error("Username/password is incorrect")

elif st.session_state.get("authentication_status") is None:
    st.warning("Please enter your username and password")