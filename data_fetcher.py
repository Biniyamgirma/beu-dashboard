import os
import pandas as pd
from sqlalchemy import text  # 1. Import text
from db_connection import create_db_engine

CSV_PATH = os.path.join(os.path.dirname(__file__), 'delivered_data.csv')


def fetch_data_all_delivered(start_date: str | None = None, end_date: str | None = None):
    if end_date is None:
        end_date = pd.Timestamp.now().normalize()
    else:
        end_date = pd.to_datetime(end_date).normalize()

    if start_date is None:
        start_date = end_date - pd.DateOffset(months=3)
    else:
        start_date = pd.to_datetime(start_date).normalize()

    # 2. Updated placeholders to named format (:start_date and :end_date)
    query = text("""
        SELECT
          orders.id AS ORDERS,
          restaurants.name AS 'Restaurant name',
          DATE_FORMAT(orders.created_at, '%Y-%m-%d %H:%i:%s') AS created_at,
          orders.coupon_discount_amount,
          restaurant_fee_details.restaurant_discount,
          restaurant_fee_details.restaurant_discount_on_food,
          restaurant_fee_details.beu_discount,
          restaurant_fee_details.beu_discount_on_food,
          restaurant_fee_details.restaurant_fee,
          restaurant_fee_details.commission_value,
          if(categories.name is not null,categories.name,'null') AS Categories_Name,
          CONCAT(admins.f_name, ' ', admins.l_name) AS 'BD NAME',
          CASE
            WHEN admins.f_name IN (
                'Yohannes',
                'Abreham',
                'Rekik',
                'Yeabtsega'
                ) THEN 'Team 1'
            WHEN admins.f_name IN (
                'Mifta',
                'Abel',
                'Cherenet',
                'Haregewyn'
                ) THEN 'Team 2'
            ELSE 'NO TEAM'
          END AS Team
        FROM
          orders
          JOIN restaurants ON restaurants.id = orders.restaurant_id
          JOIN restaurant_fee_details ON restaurant_fee_details.order_id = orders.id
          LEFT JOIN categories ON restaurants.category_id = categories.id
          JOIN admins ON admins.id = restaurants.business_developer_id
        WHERE
          DATE(orders.created_at) BETWEEN :start_date AND :end_date
          AND restaurants.name NOT LIKE 'Ethio-post%'
          AND restaurants.id NOT IN (999, 1329)
          AND orders.order_status = 'delivered'
        ORDER BY orders.created_at ASC;
    """)

    with create_db_engine().connect() as connection:
        # 3. Passed parameters as a dictionary key-value pair
        result = pd.read_sql(
            query,
            connection,
            params={
                "start_date": start_date.strftime('%Y-%m-%d'),
                "end_date": end_date.strftime('%Y-%m-%d')
            },
        )

    if not result.empty:
        result.to_csv(CSV_PATH, index=False)

    return result