import pandas as pd
from db_connection import create_engine

engine = create_engine()

def fetch_data_all_delivered():

    query = """
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
        WHEN admins.f_name IN ('Yohannes','Abreham','Yeabtsega','Rekik') THEN 'Team 1'
        WHEN admins.f_name IN ('Mifta','Cherenet','Abel','Haregewyn') THEN 'Team 2'
        ELSE 'NO TEAM'
      END AS Team
          FROM
      orders
      JOIN restaurants ON restaurants.id = orders.restaurant_id
      JOIN restaurant_fee_details ON restaurant_fee_details.order_id = orders.id
     left JOIN categories ON restaurants.category_id = categories.id
      JOIN admins ON admins.id = restaurants.business_developer_id
    WHERE
      DATE(orders.created_at) BETWEEN '2026-07-27' AND '2026-07-27'
      AND restaurants.name NOT LIKE 'Ethio-post%'
      AND restaurants.id NOT IN (999, 1329)
      AND orders.order_status = 'delivered'
    ORDER BY orders.created_at ASC;
    """
    with engine.connect() as connection:
        result = pd.read_sql(query,connection)
    return result