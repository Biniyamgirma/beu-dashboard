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
    fetch_data_all_sales,
    CSV_PATH,
    SALES_CSV_PATH,
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
def load_sales_data():
    if os.path.exists(SALES_CSV_PATH):
        df = pd.read_csv(SALES_CSV_PATH, parse_dates=["created_at"])
    else:
        df = fetch_data_all_sales()

    if df.empty:
        return df

    df["created_at"] = pd.to_datetime(df["created_at"])
    df["Date"] = df["created_at"].dt.date
    df["Time"] = df["created_at"].dt.time
    df["Hour"] = df["created_at"].dt.hour

    df["product"] = df["product"].astype(str).str.strip().str.replace(r'^"|"$', '', regex=True)
    df["category"] = df["category"].astype(str).fillna("")
    df["bd_name"] = df["bd_name"].astype(str).fillna("")
    df["Restaurant name"] = df["Restaurant name"].astype(str).fillna("")
    df["order_status"] = df["order_status"].astype(str).fillna("")
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)

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
                format="%,.0f",
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
        ["ALL Delivered", "All Sales"]
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
        m3.metric("Restaurant Discount On Food", f"{filtered_df['restaurant_discount_on_food'].sum():,.2f} ETB")

        st.metric("Coupon Discount Amount", f"{filtered_df['coupon_discount_amount'].sum():,.2f} ETB")

        
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            show_bar_table(
                filtered_df,
                group_col="BD NAME",
                value_col="commission_value",
                title="BD Performance Commission Value",
                show_rank=True,
            )

        with chart_col2:
            show_bar_table(
                filtered_df,
                group_col="Restaurant name",
                value_col="beu_discount_on_food",
                title="Restaurant beU Discount On Food",
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
                    format="%,d",
                    min_value=0,
                    max_value=safe_max_int(rest_df["commission_value"]),
                ),
                "beu_discount_on_food": st.column_config.ProgressColumn(
                    format="%,d",
                    min_value=0,
                    max_value=safe_max_int(rest_df["beu_discount_on_food"]),
                ),
                "order_count": st.column_config.ProgressColumn(
                    format="%,d",
                    min_value=0,
                    max_value=safe_max_int(rest_df["order_count"]),
                ),
            },
        )

        show_bar_table(
            filtered_df,
            group_col="BD NAME",
            value_col="commission_value",
            title="BD Performance Commission Value",
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
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No team commission data available for the current filters.")

    elif category == "All Sales":
        st.subheader("All Sales")

        if st.sidebar.button("Refresh sales data"):
            st.cache_data.clear()
            fetch_data_all_sales()
            st.success("Fetched latest sales data and updated CSV.")
            st.rerun()

        sales_df = load_sales_data()
        if sales_df.empty:
            st.warning("No sales data available. Use Refresh sales data to fetch a fresh dataset.")

        username, roles, user_full_name = get_user_info_from_config()
        is_admin = "admin" in [role.lower() for role in roles]
        is_viewer = not is_admin and "viewer" in [role.lower() for role in roles]

        if is_viewer and user_full_name:
            st.sidebar.markdown(f"**Role:** Viewer")
            st.sidebar.markdown(f"**BD Name:** {user_full_name}")
            sales_df = sales_df[sales_df["bd_name"] == user_full_name]
            if sales_df.empty:
                st.warning(f"No data available for BD Name '{user_full_name}'.")
        elif is_admin:
            st.sidebar.markdown("**Role:** Admin")
        else:
            st.sidebar.markdown("**Role:** Unknown")

        min_date = sales_df["Date"].min()
        max_date = sales_df["Date"].max()

        st.title("beU Sales Dashboard")
        date_range = st.date_input(
            "Select Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        start_time, end_time = st.slider(
            "Select Time Range",
            min_value=dt.time(0, 0),
            max_value=dt.time(23, 59),
            value=(dt.time(0, 0), dt.time(23, 59)),
            format="HH:mm",
        )

        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
        with filter_col1:
            restaurant = st.selectbox(
                "Restaurant",
                ["All"] + sorted(sales_df["Restaurant name"].dropna().unique().tolist()),
            )
        with filter_col2:
            bd_name = st.selectbox(
                "BD Name",
                ["All"] + sorted(sales_df["bd_name"].dropna().unique().tolist()),
            )
        with filter_col3:
            order_status = st.selectbox(
                "Order Status",
                ["All"] + sorted(sales_df["order_status"].dropna().unique().tolist()),
            )
        with filter_col4:
            category_name = st.selectbox(
                "Category",
                ["All"] + sorted(sales_df["category"].dropna().unique().tolist()),
            )

        search_col1, search_col2, search_col3 = st.columns(3)
        with search_col1:
            item_search = st.text_input(
                "Search by product, restaurant, category, or BD name",
                value="",
            )
        with search_col2:
            price_min = float(sales_df["price"].min())
            price_max = float(sales_df["price"].max())
            price_range = st.slider(
                "Price Range",
                min_value=price_min,
                max_value=price_max,
                value=(price_min, price_max),
                step=max(0.01, (price_max - price_min) / 100),
                format="%.2f",
            )
        with search_col3:
            qty_min = int(sales_df["quantity"].min())
            qty_max = int(sales_df["quantity"].max())
            quantity_range = st.slider(
                "Quantity Range",
                min_value=qty_min,
                max_value=qty_max,
                value=(qty_min, qty_max),
                step=1,
            )

        filtered_sales = sales_df.copy()
        if restaurant != "All":
            filtered_sales = filtered_sales[filtered_sales["Restaurant name"] == restaurant]
        if bd_name != "All":
            filtered_sales = filtered_sales[filtered_sales["bd_name"] == bd_name]
        if order_status != "All":
            filtered_sales = filtered_sales[filtered_sales["order_status"] == order_status]
        if category_name != "All":
            filtered_sales = filtered_sales[filtered_sales["category"] == category_name]

        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered_sales = filtered_sales[
                (filtered_sales["Date"] >= start_date) &
                (filtered_sales["Date"] <= end_date)
            ]

        if start_time and end_time:
            if start_time <= end_time:
                filtered_sales = filtered_sales[
                    (filtered_sales["Time"] >= start_time) &
                    (filtered_sales["Time"] <= end_time)
                ]
            else:
                filtered_sales = filtered_sales[
                    (filtered_sales["Time"] >= start_time) |
                    (filtered_sales["Time"] <= end_time)
                ]

        if item_search:
            item_lower = item_search.strip().lower()
            filtered_sales = filtered_sales[
                filtered_sales["product"].str.lower().str.contains(item_lower, na=False) |
                filtered_sales["Restaurant name"].str.lower().str.contains(item_lower, na=False) |
                filtered_sales["category"].str.lower().str.contains(item_lower, na=False) |
                filtered_sales["bd_name"].str.lower().str.contains(item_lower, na=False)
            ]

        filtered_sales = filtered_sales[
            (filtered_sales["price"] >= price_range[0]) &
            (filtered_sales["price"] <= price_range[1]) &
            (filtered_sales["quantity"] >= quantity_range[0]) &
            (filtered_sales["quantity"] <= quantity_range[1])
        ]

        st.markdown(
            f"**Sales rows:** {len(filtered_sales)}  \\  \n"
            f"**Date range:** {date_range[0]} to {date_range[1]}  \\  \n"
            f"**Time range:** {start_time} to {end_time}"
        )

        if filtered_sales.empty:
            st.info("No sales data matches the selected filters.")
        else:
            summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
            summary_col1.metric("Rows", len(filtered_sales))
            summary_col2.metric("Total Item Price", f"{(filtered_sales['price'] * filtered_sales['quantity']).sum():,.2f} ETB")
            summary_col3.metric("Total Quantity", f"{filtered_sales['quantity'].sum():,.0f}")
            summary_col4.metric("Unique Products", filtered_sales['product'].nunique())

            chart_col1, chart_col2 = st.columns(2)
            with chart_col1:
                revenue_by_restaurant = (
                    filtered_sales.assign(revenue=filtered_sales['price'] * filtered_sales['quantity'])
                    .groupby("Restaurant name", as_index=False)
                    .agg(total_revenue=("revenue", "sum"))
                    .sort_values("total_revenue", ascending=False)
                    .head(20)
                )
                fig1 = px.bar(
                    revenue_by_restaurant,
                    x="total_revenue",
                    y="Restaurant name",
                    orientation="h",
                    title="Top Restaurants by Revenue",
                    labels={"total_revenue": "Revenue", "Restaurant name": "Restaurant"},
                )
                fig1.update_layout(
                    yaxis={'categoryorder': 'total ascending', 'automargin': True},
                    xaxis_tickformat=",",
                    height=700,
                    autosize=False,
                    width=1200,
                    margin={'l': 180, 'r': 20, 't': 50, 'b': 50},
                )
                st.markdown("<div style='overflow-x:auto'>", unsafe_allow_html=True)
                st.plotly_chart(fig1, use_container_width=False, width=1200, config={"responsive": True})
                st.markdown("</div>", unsafe_allow_html=True)

            with chart_col2:
                product_counts = (
                    filtered_sales.groupby("product", as_index=False)
                    .agg(total_quantity=("quantity", "sum"))
                    .sort_values("total_quantity", ascending=False)
                    .head(20)
                )
                fig2 = px.bar(
                    product_counts,
                    x="total_quantity",
                    y="product",
                    orientation="h",
                    title="Top Products by Quantity",
                    labels={"total_quantity": "Quantity", "product": "Product"},
                )
                fig2.update_layout(
                    yaxis={'categoryorder': 'total ascending', 'automargin': True},
                    xaxis_tickformat=",",
                    height=700,
                    autosize=False,
                    width=1200,
                    margin={'l': 180, 'r': 20, 't': 50, 'b': 50},
                )
                st.markdown("<div style='overflow-x:auto'>", unsafe_allow_html=True)
                st.plotly_chart(fig2, use_container_width=False, width=1200, config={"responsive": True})
                st.markdown("</div>", unsafe_allow_html=True)

            sales_trend = (
                filtered_sales.assign(revenue=filtered_sales['price'] * filtered_sales['quantity'])
                .groupby("Date", as_index=False)["revenue"]
                .sum()
                .sort_values("Date")
            )
            fig3 = px.line(
                sales_trend,
                x="Date",
                y="revenue",
                title="Daily Revenue Trend",
                markers=True,
                labels={"revenue": "Revenue"},
            )
            fig3.update_layout(hovermode="x unified")
            st.plotly_chart(fig3, use_container_width=True)

            status_counts = (
                filtered_sales.groupby("order_status", as_index=False)["ORDERS"]
                .count()
                .sort_values("ORDERS", ascending=False)
            )
            fig4 = px.pie(
                status_counts,
                names="order_status",
                values="ORDERS",
                title="Order Status Distribution",
                hole=0.4,
            )
            st.plotly_chart(fig4, use_container_width=True)

            st.subheader("Filtered Sales Details")
            display_columns = [
                "ORDERS",
                "created_at",
                "Date",
                "Time",
                "Restaurant name",
                "product",
                "price",
                "quantity",
                "order_status",
                "category",
                "bd_name",
            ]
            display_columns = [col for col in display_columns if col in filtered_sales.columns]
            st.dataframe(
                filtered_sales.sort_values("created_at", ascending=False)[display_columns],
                use_container_width=True,
            )
    # ---- your other categories (Call Center, Area Manager, etc.) go here ----

elif st.session_state.get("authentication_status") is False:
    st.error("Username/password is incorrect")

elif st.session_state.get("authentication_status") is None:
    st.warning("Please enter your username and password")