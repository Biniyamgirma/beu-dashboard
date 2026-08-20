import streamlit as st
st.set_page_config(page_title="beU Delivery Dashboard", layout="wide")

import os
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
import pandas as pd 
import numpy as np
import datetime as dt
from datetime import timedelta
import plotly.express as px
import plotly.figure_factory as ff

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')
from data_fetcher import (
    fetch_data_all_delivered,
    fetch_data_all_sales,
    fetch_data_all_cancellations,
    fetch_marketing_budgets,
    CSV_PATH,
    SALES_CSV_PATH,
    CANCELLATIONS_CSV_PATH,
)

# 1. Get the logged-in username (usually set by streamlit-authenticator in st.session_state)
current_user = st.session_state.get("username")  # or st.session_state.get("name")

# 2. Extract roles safely from config['credentials']['usernames']


with open(CONFIG_PATH) as file:
    config = yaml.load(file, Loader=SafeLoader)

from numpy.random import default_rng as rng
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
)

user_roles = []
if current_user and current_user in config.get("credentials", {}).get("usernames", {}):
    user_roles = config["credentials"]["usernames"][current_user].get("roles", [])


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
def load_cancellations_data():
    if os.path.exists(CANCELLATIONS_CSV_PATH):
        df = pd.read_csv(CANCELLATIONS_CSV_PATH, parse_dates=["created_at"])
    else:
        df = fetch_data_all_cancellations()

    if df.empty:
        return df

    df["created_at"] = pd.to_datetime(df["created_at"])
    df["Date"] = df["created_at"].dt.date
    df["Time"] = df["created_at"].dt.time
    df["cancel_time"] = pd.to_numeric(df["cancel_time"], errors="coerce").fillna(0)
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    df["order_amount"] = pd.to_numeric(df["order_amount"], errors="coerce").fillna(0)

    df["restaurant_name"] = df["restaurant_name"].astype(str).fillna("")
    df["product"] = df["product"].astype(str).fillna("")
    df["cancellation_reason"] = df["cancellation_reason"].astype(str).fillna("")
    df["BD"] = df["BD"].astype(str).fillna("")
    df["team"] = df["team"].astype(str).fillna("")
    df["category"] = df["category"].astype(str).fillna("")

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
username, roles, user_full_name = get_user_info_from_config()


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
    categories = ["ALL Delivered", "All Sales", "All Cancellations"]

    # 4. Conditionally add 'Marketing Budget' if the user has 'marketing' or 'admin' role
    if "marketing" in roles or "admin" in roles:
        categories.append("Marketing Budget")
    # 5. Render the radio button with the filtered options list
    category = st.sidebar.radio("Select Category:", categories)

    if category == "ALL Delivered":
        st.subheader("ALL Delivered")

        if st.sidebar.button("Refresh delivered and sales data"):
            st.cache_data.clear()
            fetch_data_all_delivered()
            fetch_data_all_sales()
            st.success("Fetched latest 2-month data and updated delivered_data.csv and sales_data.csv.")
            st.rerun()

        df = load_data()

        if df.empty:
            st.warning("No delivery data available. Use Refresh delivered and sales data to fetch a fresh dataset.")
            

        
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

        # 1. CRITICAL FIX: Ensure 'Date' is strictly a Python date object for safe comparison
        df["Date"] = pd.to_datetime(df["Date"]).dt.date

        min_date = df["Date"].min()
        max_date = df["Date"].max()

        st.title("beU Delivery Dashboard")
        
        date_range = st.date_input(
            "Select Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
        
        # 2. CRITICAL FIX: Safely parse Streamlit's date_input state
        if len(date_range) == 2:
            start_date, end_date = date_range
        elif len(date_range) == 1:
            # When user clicks the first date but hasn't clicked the second yet
            start_date = date_range[0]
            end_date = date_range[0]
        else:
            start_date, end_date = min_date, max_date

        # Calculate previous period dates
        num_days = (end_date - start_date).days + 1
        prev_end_date = start_date - timedelta(days=1)
        prev_start_date = start_date - timedelta(days=num_days)

        st.subheader("Filters")
        col1, col2, col3, col4 = st.columns(4)

        # 3. CRITICAL FIX: Base the dropdowns ONLY on the selected dates!
        df_date_filtered = df[(df["Date"] >= start_date) & (df["Date"] <= end_date)]
        
        # Initialize session states safely based on the date-filtered data
        if "delivery_bd_name" not in st.session_state:
            st.session_state.delivery_bd_name = sorted(df_date_filtered["BD NAME"].dropna().unique().tolist())
        if "delivery_restaurant" not in st.session_state:
            st.session_state.delivery_restaurant = sorted(df_date_filtered["Restaurant name"].dropna().unique().tolist())
        if "delivery_team" not in st.session_state:
            st.session_state.delivery_team = sorted(df_date_filtered["Team"].dropna().unique().tolist())
        if "delivery_category" not in st.session_state:
            st.session_state.delivery_category = sorted(df_date_filtered["Categories_Name"].dropna().unique().tolist())

        # --- Dropdown UI Logic ---
        with col1:
            all_bds = sorted(df_date_filtered["BD NAME"].dropna().unique().tolist())
            filtered_bd = [x for x in st.session_state.delivery_bd_name if x in all_bds]
            if not filtered_bd and all_bds: filtered_bd = all_bds
                
            bd_name = st.multiselect("BD Name", all_bds, default=filtered_bd, key="delivery_bd_select", disabled=is_viewer)
            st.session_state.delivery_bd_name = bd_name

        with col2:
            temp_df = df_date_filtered.copy()
            if bd_name: temp_df = temp_df[temp_df["BD NAME"].isin(bd_name)]
            
            available_restaurants = sorted(temp_df["Restaurant name"].dropna().unique().tolist())
            filtered_restaurant = [x for x in st.session_state.delivery_restaurant if x in available_restaurants]
            if not filtered_restaurant and available_restaurants: filtered_restaurant = available_restaurants
                
            restaurant = st.multiselect("Restaurant", available_restaurants, default=filtered_restaurant, key="delivery_restaurant_select")
            st.session_state.delivery_restaurant = restaurant

        with col3:
            if restaurant: temp_df = temp_df[temp_df["Restaurant name"].isin(restaurant)]
            
            available_teams = sorted(temp_df["Team"].dropna().unique().tolist())
            filtered_team = [x for x in st.session_state.delivery_team if x in available_teams]
            if not filtered_team and available_teams: filtered_team = available_teams
            
            team = st.multiselect("Team", available_teams, default=filtered_team, key="delivery_team_select")
            st.session_state.delivery_team = team

        with col4:
            import numpy as np
            temp_df["Categories_Name"] = temp_df["Categories_Name"].replace(r'^\s*$', np.nan, regex=True).fillna("Blank")
            
            available_categories = sorted(temp_df["Categories_Name"].unique().tolist())
            # 2. CRITICAL FIX: Safely initialize session state if it doesn't exist
            if "sales_category" not in st.session_state:
                st.session_state.sales_category = available_categories

            filtered_category = [x for x in st.session_state.sales_category if x in available_categories]
            if not filtered_category and available_categories:
                filtered_category = available_categories
            
            # 3. CRITICAL FIX: Use the 'filtered_category' variable you just calculated for the default!
            category_name = st.multiselect(
                "Category",
                options=available_categories,
                default=filtered_category,
                key="sales_category_select_v2"  # <-- ADD _v2 HERE
            )
            st.session_state.sales_category = category_name

        # --- Final Dataframe Creation ---
        # Apply the selected dropdowns to the ENTIRE dataframe first
        master_filtered_df = df.copy()
        

        if bd_name:
            master_filtered_df = master_filtered_df[master_filtered_df["BD NAME"].isin(bd_name)]
            
        if restaurant:
            master_filtered_df = master_filtered_df[master_filtered_df["Restaurant name"].isin(restaurant)]
            
        if team:
            master_filtered_df = master_filtered_df[master_filtered_df["Team"].isin(team)]
            
        if category_name:
            if "Blank" in category_name:
                # Remove "Blank" from the list of words to search for
                valid_cats = [c for c in category_name if c != "Blank"]
                
                # Match the valid categories OR any rows that are NaN/Empty
                master_filtered_df = master_filtered_df[
                    master_filtered_df["Categories_Name"].isin(valid_cats) | 
                    master_filtered_df["Categories_Name"].isna() | 
                    (master_filtered_df["Categories_Name"] == "") |
                    (master_filtered_df["Categories_Name"] == " ")
                ]
            else:
                # Normal filtering if "Blank" is not selected
                master_filtered_df = master_filtered_df[master_filtered_df["Categories_Name"].isin(category_name)]
            

        
        # Split into Current Period and Previous Period for metrics
        filtered_df = master_filtered_df[
            (master_filtered_df["Date"] >= start_date) & 
            (master_filtered_df["Date"] <= end_date)
        ]
        
        prev_df = master_filtered_df[
            (master_filtered_df["Date"] >= prev_start_date) & 
            (master_filtered_df["Date"] <= prev_end_date)
        ]

        def get_metric_delta(curr_val: float, prev_val: float) -> str:
            if prev_val == 0:
                return "+100.0%" if curr_val > 0 else ("0.0%" if curr_val == 0 else "-100.0%")
            pct_change = ((curr_val - prev_val) / abs(prev_val)) * 100
            return f"{pct_change:+.1f}% vs prev {prev_val} period"
        
        def compute_metric(col_name, agg_type="sum", currency="ETB"):
            # Check if column exists to prevent KeyErrors
            col_exists_curr = col_name in filtered_df.columns
            col_exists_prev = col_name in prev_df.columns

            if agg_type == "nunique":
                # Count unique values (Best for counting distinct orders)
                curr_val = filtered_df[col_name].nunique() if not filtered_df.empty and col_exists_curr else 0
                prev_val = prev_df[col_name].nunique() if not prev_df.empty and col_exists_prev else 0
                val_str = f"{curr_val:,}"
                
            elif agg_type == "sum":
                # Sum the values (Best for currency and financial metrics)
                curr_val = filtered_df[col_name].sum() if not filtered_df.empty and col_exists_curr else 0.0
                prev_val = prev_df[col_name].sum() if not prev_df.empty and col_exists_prev else 0.0
                val_str = f"{curr_val:,.2f} {currency}"
                
            else:
                curr_val, prev_val = 0, 0
                val_str = "0"

            # Always calculate delta, even if prev_df is technically empty (so 0 to X shows as +100%)
            delta_str = get_metric_delta(curr_val, prev_val)
            return val_str, delta_str

        # --- Metrics Display ---
        st.subheader("Performance Overview")
        
        # Metric Definitions: (Label, Column Name, Aggregation Type)
        metrics_config = [
            ("Total Orders", "ORDERS", "nunique"),  # Make sure "ORDERS" matches your exact dataframe column name!
            ("Commission Value", "commission_value", "sum"),
            ("Restaurant Fee", "restaurant_fee", "sum"),
            ("Restaurant Discount", "restaurant_discount", "sum"),
            ("beU Discount", "beu_discount", "sum"),
            ("beU Discount On Food", "beu_discount_on_food", "sum"),
            ("Restaurant Discount On Food", "restaurant_discount_on_food", "sum"),
            ("Coupon Discount Amount", "coupon_discount_amount", "sum"),
        ]

        # Render dynamically in a 3-column grid
        cols = st.columns(3)
        for idx, (label, col_name, agg_type) in enumerate(metrics_config):
            val_str, delta_str = compute_metric(col_name=col_name, agg_type=agg_type)
            cols[idx % 3].metric(
                label=label,
                value=val_str,
                delta=delta_str,
                delta_color="normal"  # Green for positive, Red for negative
            )

        #
        
        
        chart_col1, chart_col2 = st.columns(2)

        # with chart_col1:
        #     show_bar_table(
        #         filtered_df,
        #         group_col="BD NAME",
        #         value_col="commission_value",
        #         title="BD Performance Commission Valu",
        #         show_rank=True,
        #     )


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
        # This will display the actual list of available columns on your dashboard
        # st.write("Actual columns in rest_df:", rest_df.columns.tolist())
        cols_to_show = ["ORDERS", "Restaurant name","created_at","restaurant_discount","restaurant_discount_on_food","restaurant_fee","BD NAME"]
        st.header("Restaurant Sales Report")
        st.dataframe(filtered_df[cols_to_show])

        samp_df = filtered_df.groupby(["BD NAME"], as_index=False).agg(
                                            ORDERS=("ORDERS", "count"),
                                            TOTAL_COMMISSION=("commission_value", "sum") # Replace with your actual commission column name
                                        ).sort_values(["BD NAME"])
        st.dataframe(samp_df)

        if not filtered_df.empty:
            team_commission = (
                filtered_df.groupby(["Date", "Team"], as_index=False)
                ["ORDERS"]
                .count()
                .sort_values(["Team", "Date"])
            )

            fig = px.line(
                team_commission,
                x="Date",
                y="ORDERS",
                color="Team",
                markers=True,
                title="Team Delivered Order Performance",
                labels={
                    "Order_count": "Order_count",
                    "Date": "Date",
                },
            )
            fig.update_layout(hovermode="x unified")
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No team Order count data available for the current filters.")

    elif category == "All Sales":
        st.subheader("All Sales")

        if st.sidebar.button("Refresh delivered and sales data"):
            st.cache_data.clear()
            fetch_data_all_delivered()
            fetch_data_all_sales()
            st.success("Fetched latest 2-month data and updated delivered_data.csv and sales_data.csv.")
            st.rerun()

        sales_df = load_sales_data()
        if sales_df.empty:
            st.warning("No sales data available. Use Refresh delivered and sales data to fetch a fresh dataset.")

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

        # Initialize session state for sales filters
        if "sales_restaurant" not in st.session_state:
            st.session_state.sales_restaurant = sorted(sales_df["Restaurant name"].dropna().unique().tolist())
        if "sales_bd_name" not in st.session_state:
            bd_opts = sorted(sales_df["bd_name"].dropna().unique().tolist())
            if is_viewer and user_full_name:
                st.session_state.sales_bd_name = [user_full_name] if user_full_name in bd_opts else bd_opts
            else:
                st.session_state.sales_bd_name = bd_opts
        if "sales_status" not in st.session_state:
            st.session_state.sales_status = sorted(sales_df["order_status"].dropna().unique().tolist())
        if "sales_category" not in st.session_state:
            st.session_state.sales_category = sorted(sales_df["category"].dropna().unique().tolist())

        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
        
        # Restaurant Filter
        with filter_col1:
            all_restaurants = sorted(sales_df["Restaurant name"].dropna().unique().tolist())
            restaurant = st.multiselect(
                "Restaurant",
                all_restaurants,
                default=st.session_state.sales_restaurant,
                key="sales_restaurant_select",
                placeholder="Search & select restaurants..."
            )
            st.session_state.sales_restaurant = restaurant
            if restaurant:
                st.caption(f"✓ {len(restaurant)} selected")
        
        # BD Name Filter - filtered based on restaurant selection
        with filter_col2:
            temp_df = sales_df.copy()
            if restaurant:
                temp_df = temp_df[temp_df["Restaurant name"].isin(restaurant)]
            available_bd = sorted(temp_df["bd_name"].dropna().unique().tolist())
            
            filtered_bd = [x for x in st.session_state.sales_bd_name if x in available_bd]
            if not filtered_bd and available_bd:
                filtered_bd = available_bd if not is_viewer else [x for x in available_bd if x == user_full_name]
            
            bd_name = st.multiselect(
                "BD Name",
                available_bd,
                default=filtered_bd,
                key="sales_bd_select",
                placeholder="Search & select BD names..."
            )
            st.session_state.sales_bd_name = bd_name
            if bd_name:
                st.caption(f"✓ {len(bd_name)} selected")
        
        # Order Status Filter - filtered based on restaurant and BD selection
        with filter_col3:
            temp_df = sales_df.copy()
            if restaurant:
                temp_df = temp_df[temp_df["Restaurant name"].isin(restaurant)]
            if bd_name:
                temp_df = temp_df[temp_df["bd_name"].isin(bd_name)]
            available_status = sorted(temp_df["order_status"].dropna().unique().tolist())
            
            filtered_status = [x for x in st.session_state.sales_status if x in available_status]
            if not filtered_status and available_status:
                filtered_status = available_status
            
            order_status = st.multiselect(
                "Order Status",
                available_status,
                default=filtered_status,
                key="sales_status_select",
                placeholder="Search & select status..."
            )
            st.session_state.sales_status = order_status
            if order_status:
                st.caption(f"✓ {len(order_status)} selected")
        
        # Category Filter - filtered based on all previous selections
        with filter_col4:
            temp_df = sales_df.copy()
            if restaurant:
                temp_df = temp_df[temp_df["Restaurant name"].isin(restaurant)]
            if bd_name:
                temp_df = temp_df[temp_df["bd_name"].isin(bd_name)]
            if order_status:
                temp_df = temp_df[temp_df["order_status"].isin(order_status)]

            # 1. CRITICAL FIX: Catch empty strings AND NaNs, and convert them to "Blank"
            # Replace empty strings or spaces with NaN first, then fill all NaNs with "Blank"
            import numpy as np
            temp_df["category"] = temp_df["category"].replace(r'^\s*$', np.nan, regex=True).fillna("Blank")
            
            available_categories = sorted(temp_df["category"].unique().tolist())
            # 2. CRITICAL FIX: Safely initialize session state if it doesn't exist
            if "sales_category" not in st.session_state:
                st.session_state.sales_category = available_categories

            filtered_category = [x for x in st.session_state.sales_category if x in available_categories]
            if not filtered_category and available_categories:
                filtered_category = available_categories
            
            # 3. CRITICAL FIX: Use the 'filtered_category' variable you just calculated for the default!
            category_name = st.multiselect(
                "Category",
                options=available_categories,
                default=filtered_category,
                key="sales_category_select_v2"  # <-- ADD _v2 HERE
            )
            st.session_state.sales_category = category_name
            if category_name:
                st.caption(f"✓ {len(category_name)} selected")

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
        if restaurant:
            filtered_sales = filtered_sales[filtered_sales["Restaurant name"].isin(restaurant)]
        if bd_name:
            filtered_sales = filtered_sales[filtered_sales["bd_name"].isin(bd_name)]
        if order_status:
            filtered_sales = filtered_sales[filtered_sales["order_status"].isin(order_status)]
        
        # 4. CRITICAL FIX: Teach the dataframe how to filter when the user selects "Blank"
        if category_name:
            if "Blank" in category_name:
                valid_cats = [c for c in category_name if c != "Blank"]
                # Match the valid categories OR any rows that are NaN/Empty
                filtered_sales = filtered_sales[
                    filtered_sales["category"].isin(valid_cats) | 
                    filtered_sales["category"].isna() | 
                    (filtered_sales["category"] == "") |
                    (filtered_sales["category"] == " ")
                ]
            else:
                filtered_sales = filtered_sales[filtered_sales["category"].isin(category_name)]

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
            f"**Date range:** {date_range[0]} to {date_range[1]}  \\  \n"
            f"**Time range:** {start_time} to {end_time}"
        )

        if filtered_sales.empty:
            st.info("No sales data matches the selected filters.")
        else:
            summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
            summary_col1.metric("Total Item Price", f"{(filtered_sales['price'] * filtered_sales['quantity']).sum():,.2f} ETB")
            summary_col2.metric("Total Quantity", f"{filtered_sales['quantity'].sum():,.0f}")
            summary_col3.metric("Unique Products", filtered_sales['product'].nunique())

        chart_col1, chart_col2 = st.columns(2)

        # ----------------------------------------------------
        # Column 1: Top Restaurants by Restaurant Fee
        # ----------------------------------------------------
        with chart_col1:
            st.subheader("Top Restaurants by Restaurant item price")
            
            revenue_by_restaurant = (
                filtered_sales.assign(restaurant_item_price=filtered_sales['price'] * filtered_sales['quantity'])
                .groupby("Restaurant name", as_index=False)
                .agg(total_res_item_price=("restaurant_item_price", "sum"))
                .sort_values("total_res_item_price", ascending=False)
                .head(20)
                .reset_index(drop=True)
            )

            # Display formatted table
            st.dataframe(
                revenue_by_restaurant,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Restaurant name": st.column_config.TextColumn("Restaurant"),
                    "total_res_item_price": st.column_config.NumberColumn(
                        "Restaurant Item price",
                        format="%.2f ETB",
                    ),
                },
            )

            # CSV Download Button
            csv_restaurants = revenue_by_restaurant.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=" Download Top Restaurants CSV",
                data=csv_restaurants,
                file_name="top_restaurants_item_price.csv",
                mime="text/csv",
                use_container_width=True,
                key="download_top_restaurants"
            )

        # ----------------------------------------------------
        # Column 2: Top Products by Quantity
        # ----------------------------------------------------
        with chart_col2:
            st.subheader("Top Products by Quantity")
            
            product_counts = (
                filtered_sales.groupby("product", as_index=False)
                .agg(total_quantity=("quantity", "sum"))
                .sort_values("total_quantity", ascending=False)
                .head(20)
                .reset_index(drop=True)
            )

            # Display formatted table with visual progress indicators
            max_qty = int(product_counts["total_quantity"].max()) if not product_counts.empty else 100
            st.dataframe(
                product_counts,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "product": st.column_config.TextColumn("Product"),
                    "total_quantity": st.column_config.ProgressColumn(
                        "Total Quantity",
                        format="%d",
                        min_value=0,
                        max_value=max_qty,
                    ),
                },
            )

            # CSV Download Button
            csv_products = product_counts.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Top Products CSV",
                data=csv_products,
                file_name="top_products_quantity.csv",
                mime="text/csv",
                use_container_width=True,
                key="download_top_products"
            )

            sales_trend = (
                filtered_sales.assign(price= filtered_sales['quantity'])
                .groupby("Date", as_index=False)["quantity"]
                .sum()
                .sort_values("Date")
            )
        fig3 = px.line(
            sales_trend,
            x="Date",
            y="quantity",
            title="Daily Sales Trend",
            markers=True,
            labels={"Quantity": "Price"},
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

    elif category == "All Cancellations":
        st.subheader("All Cancellations")

        if st.sidebar.button("Refresh cancellations data"):
            st.cache_data.clear()
            fetch_data_all_cancellations()
            st.success("Fetched latest 2-month cancellation data and updated cancellations_data.csv.")
            st.rerun()

        cancel_df = load_cancellations_data()
        if cancel_df.empty:
            st.warning("No cancellation data available. Use Refresh cancellations data to fetch a fresh dataset.")

        username, roles, first_name = get_user_info_from_config()
        is_admin = "admin" in [role.lower() for role in roles]
        is_viewer = not is_admin and "viewer" in [role.lower() for role in roles]

        if is_viewer and first_name:
            st.sidebar.markdown(f"**Role:** Viewer")
            st.sidebar.markdown(f"**BD Name:** {first_name}")
            cancel_df = cancel_df[cancel_df["BD"] == first_name]
            if cancel_df.empty:
                st.warning(f"No data available for BD Name '{first_name}'.")
        elif is_admin:
            st.sidebar.markdown("**Role:** Admin")
        else:
            st.sidebar.markdown("**Role:** Unknown")

        min_date = cancel_df["Date"].min()
        max_date = cancel_df["Date"].max()

        st.title("beU Cancellation Dashboard")
        date_range = st.date_input(
            "Select Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        # Initialize session state for cancellation filters
        if "cancel_bd_name" not in st.session_state:
            bd_opts = sorted(cancel_df["BD"].dropna().unique().tolist())
            if is_viewer and first_name:
                st.session_state.cancel_bd_name = [first_name] if first_name in bd_opts else bd_opts
            else:
                st.session_state.cancel_bd_name = bd_opts
        if "cancel_restaurant" not in st.session_state:
            st.session_state.cancel_restaurant = sorted(cancel_df["restaurant_name"].dropna().unique().tolist())
        if "cancel_team" not in st.session_state:
            st.session_state.cancel_team = sorted(cancel_df["team"].dropna().unique().tolist())
        if "cancel_category" not in st.session_state:
            st.session_state.cancel_category = sorted(cancel_df["category"].dropna().unique().tolist())
        if "cancel_reason" not in st.session_state:
            st.session_state.cancel_reason = sorted(cancel_df["cancellation_reason"].dropna().unique().tolist())

        # Create 5 columns instead of 4 to accommodate the new filter
        col1, col2, col3= st.columns(3)
        
        # 1. BD Name Filter (Moved to first so it dictates available restaurants)
        with col1:
            available_bd = sorted(cancel_df["BD"].dropna().unique().tolist())
            filtered_bd = [x for x in st.session_state.cancel_bd_name if x in available_bd]
            
            if not filtered_bd and available_bd:
                filtered_bd = available_bd if not is_viewer else [x for x in available_bd if x == first_name]
            
            bd_name = st.multiselect(
                "BD Name",
                available_bd,
                default=filtered_bd,
                key="cancel_bd_select",
                placeholder="Select BD..."
            )
            st.session_state.cancel_bd_name = bd_name
            if bd_name:
                st.caption(f"✓ {len(bd_name)} selected")

        # 2. Restaurant Filter - filtered based on BD selection
        with col2:
            temp_df = cancel_df.copy()
            if bd_name:
                temp_df = temp_df[temp_df["BD"].isin(bd_name)]
                
            available_restaurants = sorted(temp_df["restaurant_name"].dropna().unique().tolist())
            
            # This logic automatically drops selected restaurants if they don't belong to the newly selected BD
            filtered_rest = [x for x in st.session_state.cancel_restaurant if x in available_restaurants]
            if not filtered_rest and available_restaurants:
                filtered_rest = available_restaurants
                
            restaurant = st.multiselect(
                "Restaurant",
                available_restaurants,
                default=filtered_rest,
                key="cancel_restaurant_select",
                placeholder="Select Rest..."
            )
            st.session_state.cancel_restaurant = restaurant
            if restaurant:
                st.caption(f"✓ {len(restaurant)} selected")
        col4, col5 = st.columns(2)
        # 3. Team Filter - filtered based on BD and Restaurant
        with col3:
            if restaurant:
                temp_df = temp_df[temp_df["restaurant_name"].isin(restaurant)]
                
            available_teams = sorted(temp_df["team"].dropna().unique().tolist())
            
            filtered_team = [x for x in st.session_state.cancel_team if x in available_teams]
            if not filtered_team and available_teams:
                filtered_team = available_teams
            
            team = st.multiselect(
                "Team",
                available_teams,
                default=filtered_team,
                key="cancel_team_select",
                placeholder="Select teams..."
            )
            st.session_state.cancel_team = team
            if team:
                st.caption(f"✓ {len(team)} selected")
        
        # 4. Category Filter - filtered based on previous selections
        with col4:
            import numpy as np
            # Replace empty strings/spaces with NaN, then fill with "Blank"
            temp_df["category"] = temp_df["category"].replace(r'^\s*$', np.nan, regex=True).fillna("Blank")
            
            available_categories = sorted(temp_df["category"].unique().tolist())
            
            # CRITICAL FIX 1: Use a unique session state name for the Cancel tab!
            if "cancel_category" not in st.session_state:
                st.session_state.cancel_category = available_categories

            filtered_category = [x for x in st.session_state.cancel_category if x in available_categories]
            if not filtered_category and available_categories:
                filtered_category = available_categories
            
            category_name = st.multiselect(
                "Category",
                options=available_categories,
                default=filtered_category,
                key="cancel_category_select"  # Unique key for Cancel tab
            )
            st.session_state.cancel_category = category_name
            if category_name:
                st.caption(f"✓ {len(category_name)} selected")

        # 5. Cancellation Reason Filter - filtered based on all previous selections
        with col5:
            if category_name:
                temp_df = temp_df[temp_df["category"].isin(category_name)]
                
            available_reasons = sorted(temp_df["cancellation_reason"].dropna().unique().tolist())
            
            # Use unique session state for cancellation reason
            if "cancel_reason" not in st.session_state:
                st.session_state.cancel_reason = available_reasons

            filtered_reason = [x for x in st.session_state.cancel_reason if x in available_reasons]
            if not filtered_reason and available_reasons:
                filtered_reason = available_reasons
                
            cancel_reason = st.multiselect(
                "Reason",
                available_reasons,
                default=filtered_reason,
                key="cancel_reason_select",
                placeholder="Select Reason..."
            )
            st.session_state.cancel_reason = cancel_reason
            if cancel_reason:
                st.caption(f"✓ {len(cancel_reason)} selected")

        search_col1, search_col2 = st.columns(2)
        with search_col1:
            reason_search = st.text_input(
                "Search by restaurant, product, BD, or cancellation reason",
                value="",
            )

        # Apply ALL filters to the final dataframe
        filtered_cancel_df = cancel_df.copy()
        if bd_name:
            filtered_cancel_df = filtered_cancel_df[filtered_cancel_df["BD"].isin(bd_name)]
        if restaurant:
            filtered_cancel_df = filtered_cancel_df[filtered_cancel_df["restaurant_name"].isin(restaurant)]
        if team:
            filtered_cancel_df = filtered_cancel_df[filtered_cancel_df["team"].isin(team)]
            
        if category_name:
            if "Blank" in category_name:
                # Remove "Blank" from the list of words to search for
                valid_cats = [c for c in category_name if c != "Blank"]
                
                # CRITICAL FIX 2: Assign back to filtered_cancel_df, NOT master_filtered_df
                filtered_cancel_df = filtered_cancel_df[
                    filtered_cancel_df["category"].isin(valid_cats) | 
                    filtered_cancel_df["category"].isna() | 
                    (filtered_cancel_df["category"] == "") |
                    (filtered_cancel_df["category"] == " ")
                ]
            else:
                # Normal filtering if "Blank" is not selected
                filtered_cancel_df = filtered_cancel_df[filtered_cancel_df["category"].isin(category_name)]
            
        if cancel_reason:
            filtered_cancel_df = filtered_cancel_df[filtered_cancel_df["cancellation_reason"].isin(cancel_reason)]
        # Apply Date Range
        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered_cancel_df = filtered_cancel_df[
                (filtered_cancel_df["Date"] >= start_date) &
                (filtered_cancel_df["Date"] <= end_date)
            ]

        # Apply Search Query
        if reason_search:
            search_lower = reason_search.strip().lower()
            filtered_cancel_df = filtered_cancel_df[
                filtered_cancel_df["restaurant_name"].str.lower().str.contains(search_lower, na=False) |
                filtered_cancel_df["product"].str.lower().str.contains(search_lower, na=False) |
                filtered_cancel_df["cancellation_reason"].str.lower().str.contains(search_lower, na=False) |
                filtered_cancel_df["BD"].str.lower().str.contains(search_lower, na=False)
            ]

        summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
        summary_col1.metric("Quantity", len(filtered_cancel_df))
        summary_col2.metric("Avg Cancel Time", f"{filtered_cancel_df['cancel_time'].mean():.1f} mins")
        summary_col3.metric("Number of Order", filtered_cancel_df['id'].nunique())
        if filtered_cancel_df.empty:
            st.info("No cancellation data matches the selected filters.")
        else:
            st.subheader("Cancellation Reason Counts")
            reason_summary = (
                filtered_cancel_df.groupby("cancellation_reason", as_index=False)["id"]
                .count()
                .rename(columns={"id": "count"})
                .sort_values("count", ascending=False)
            )
            
            # Replaced the bar chart with a table format
            st.dataframe(
                reason_summary, 
                use_container_width=True, 
                hide_index=True
            )
            team_summary = (
                filtered_cancel_df.groupby("team", as_index=False)["id"]
                .count()
                .rename(columns={"id": "count"})
            )
            fig_team = px.pie(
                team_summary,
                names="team",
                values="count",
                title="Cancellations by Team",
            )
            st.plotly_chart(fig_team, use_container_width=True)

            st.subheader("Cancellation Summary")

            # Group by the required columns and count unique order IDs
            # Note: Ensure "order_id" matches the actual column name in your DataFrame
            aggregated_cancel_df = (
                filtered_cancel_df.groupby(["restaurant_name", "BD", "cancellation_reason"])["id"]
                .nunique()
                .reset_index(name="total_unique_orders")
            )
            st.dataframe(
                aggregated_cancel_df.sort_values("total_unique_orders", ascending=False),
                use_container_width=True,
            )
            
            st.subheader("Cancellation Details")
            display_columns = [
                "id",
                "created_at",
                "Date",
                "Time",
                "restaurant_name",
                "product",
                "unit_price",
                "quantity",
                "delivery_charge",
                "order_amount",
                "cancellation_reason",
                "order_status",
                "BD",
                "team",
                "cancel_time",
                "category",
            ]
            display_columns = [col for col in display_columns if col in filtered_cancel_df.columns]
            st.dataframe(
                filtered_cancel_df.sort_values("created_at", ascending=False)[display_columns],
                use_container_width=True,
            )
    # 3. Use user_roles in your condition
    elif category == "Marketing Budget" and ("admin" in user_roles or "marketing" in user_roles):
        st.subheader("Marketing Budget")
        today = dt.date.today()
        seven_days_ago = today - dt.timedelta(days=7)

        date_range = st.date_input(
            "Select Date Range",
            value=(seven_days_ago, today)
        )

        if(len(date_range)==2):
            start_date, end_date = date_range
            df = fetch_marketing_budgets(start_date,end_date)

            ##transpose the result
            df_transposed = df.T

            st.subheader("Result")
            st.dataframe(df_transposed)
        else:
            st.info("Please select both a start and end date.")

    # Your logic here
    # ---- your other categories (Call Center, Area Manager, etc.) go here ----

elif st.session_state.get("authentication_status") is False:
    st.error("Username/password is incorrect")

elif st.session_state.get("authentication_status") is None:
    st.warning("Please enter your username and password")