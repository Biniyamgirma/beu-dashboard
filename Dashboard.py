import streamlit as st
st.set_page_config(page_title="beU Delivery Dashboard", layout="wide")

import os
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
import pandas as pd 
import numpy as np
import datetime as dt
import plotly.express as px
import plotly.figure_factory as ff

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')
from data_fetcher import (
    fetch_data_all_delivered,
    CSV_PATH,
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
    if os.path.exists(CSV_PATH):
        df = pd.read_csv(CSV_PATH, parse_dates=["created_at"])
    else:
        df = fetch_data_all_delivered()

    if df.empty:
        return df

    df["created_at"] = pd.to_datetime(df["created_at"])
    df["Date"] = df["created_at"].dt.date
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


def get_user_info_from_config():
    username = st.session_state.get("username") or st.session_state.get("name")
    if not username:
        return None, [], None

    credentials = config.get("credentials", {}).get("usernames", {})
    user_info = credentials.get(username)

    if user_info is None:
        for key, info in credentials.items():
            full_name = f"{info.get('first_name', '').strip()} {info.get('last_name', '').strip()}".strip()
            if username == key or username == info.get('email') or username == full_name:
                user_info = info
                username = key
                break

    if user_info is None:
        return username, [], None

    roles = user_info.get("roles", [])
    if isinstance(roles, str):
        roles = [roles]

    full_name = f"{user_info.get('first_name', '').strip()} {user_info.get('last_name', '').strip()}".strip()
    return username, roles, full_name


def safe_max_int(series):
    try:
        value = series.max()
        if pd.isna(value):
            return 0
        return int(value)
    except (ValueError, TypeError):
        return 0


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
                max_value=safe_max_int(agg[value_col]),
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
        ["ALL Delivered", "new"]
    )

    if category == "ALL Delivered":
        st.subheader("ALL Delivered")

        if st.sidebar.button("Refresh delivered data"):
            st.cache_data.clear()
            fetch_data_all_delivered()
            st.success("Fetched latest 3-month data and updated CSV.")
            st.rerun()

        df = load_data()

        if df.empty:
            st.warning("No delivery data available. Use Refresh delivered data to fetch a fresh dataset.")
            

        username, roles, user_full_name = get_user_info_from_config()
        is_admin = "admin" in [role.lower() for role in roles]
        is_viewer = not is_admin and "viewer" in [role.lower() for role in roles]

        if is_viewer and user_full_name:
            st.sidebar.markdown(f"**Role:** Viewer")
            st.sidebar.markdown(f"**BD Name:** {user_full_name}")
            df = df[df["BD NAME"] == user_full_name]
            if df.empty:
                st.warning(f"No data available for BD Name '{user_full_name}'.")
                
        elif is_admin:
            st.sidebar.markdown("**Role:** Admin")
        else:
            st.sidebar.markdown("**Role:** Unknown")

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
            restaurant = st.selectbox(
                "Restaurant",
                ["All"] + sorted(df["Restaurant name"].dropna().unique().tolist()),
            )

        with col2:
            bd_name = st.selectbox(
                "BD Name",
                ["All"] + sorted(df["BD NAME"].dropna().unique().tolist()),
            )

        with col3:
            team = st.selectbox(
                "Team",
                ["All"] + sorted(df["Team"].dropna().unique().tolist()),
            )

        with col4:
            category_name = st.selectbox(
                "Category",
                ["All"] + sorted(df["Categories_Name"].dropna().unique().tolist()),
            )

        filtered_df = df.copy()

        if restaurant != "All":
            filtered_df = filtered_df[filtered_df["Restaurant name"] == restaurant]

        if bd_name != "All":
            filtered_df = filtered_df[filtered_df["BD NAME"] == bd_name]

        if team != "All":
            filtered_df = filtered_df[filtered_df["Team"] == team]

        if category_name != "All":
            filtered_df = filtered_df[filtered_df["Categories_Name"] == category_name]

        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = filtered_df[
                (filtered_df["Date"] >= start_date) &
                (filtered_df["Date"] <= end_date)
            ]

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Orders", len(filtered_df))
        m2.metric("Commission Value", f"{filtered_df['commission_value'].sum():,.2f} ETB")
        m3.metric("Restaurant Fee", f"{filtered_df['restaurant_fee'].sum():,.2f} ETB")

        m1.metric("Restaurant Discount", f"{filtered_df['restaurant_discount'].sum():,.2f} ETB")
        m2.metric("beU Discount", f"{filtered_df['beu_discount'].sum():,.2f} ETB")
        m3.metric("beU Discount On Food", f"{filtered_df['beu_discount_on_food'].sum():,.2f} ETB")

        st.metric("Coupon Discount Amount", f"{filtered_df['coupon_discount_amount'].sum():,.2f} ETB")

        
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

        rest_df = (
            filtered_df.groupby(["Restaurant name", "BD NAME"], as_index=False)
            .agg(
                commission_value=("commission_value", "sum"),
                beu_discount_on_food=("beu_discount_on_food", "sum"),
                order_count=("ORDERS", "nunique"),
            )
            .sort_values("commission_value", ascending=False)
        )

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
                    max_value=safe_max_int(rest_df["commission_value"]),
                ),
                "beu_discount_on_food": st.column_config.ProgressColumn(
                    "beu_discount_on_food",
                    format="%d",
                    min_value=0,
                    max_value=safe_max_int(rest_df["beu_discount_on_food"]),
                ),
                "order_count": st.column_config.ProgressColumn(
                    "order_count",
                    format="%d",
                    min_value=0,
                    max_value=safe_max_int(rest_df["order_count"]),
                ),
            },
        )

        show_bar_table(
            filtered_df,
            group_col="BD NAME",
            value_col="commission_value",
            title="BD Performance — Commission Value",
            show_rank=True,
        )

        if not filtered_df.empty:
            team_commission = (
                filtered_df.groupby(["Date", "Team"], as_index=False)
                ["commission_value"]
                .sum()
                .sort_values(["Team", "Date"])
            )

            fig = px.line(
                team_commission,
                x="Date",
                y="commission_value",
                color="Team",
                markers=True,
                title="Team Commission Performance",
                labels={
                    "commission_value": "Commission Value (ETB)",
                    "Date": "Date",
                },
            )
            fig.update_layout(hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No team commission data available for the current filters.")
    # ---- your other categories (Call Center, Area Manager, etc.) go here ----

elif st.session_state.get("authentication_status") is False:
    st.error("Username/password is incorrect")

elif st.session_state.get("authentication_status") is None:
    st.warning("Please enter your username and password")