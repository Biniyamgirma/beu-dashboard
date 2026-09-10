import os
import time
import tempfile
import logging
import pandas as pd
from sqlalchemy import inspect, text
from db_connection import create_db_engine

CSV_PATH = os.path.join(os.path.dirname(__file__), 'delivered_data.csv')
SALES_CSV_PATH = os.path.join(os.path.dirname(__file__), 'sales_data.csv')
CANCELLATIONS_CSV_PATH = os.path.join(os.path.dirname(__file__), 'cancellations_data.csv')


def _supports_item_columns() -> bool:
    engine = create_db_engine()
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    return "order_items" in tables and "menu_items" in tables


def fetch_data_all_sales(start_date: str | None = None,end_date: str | None = None):
    if start_date is None and end_date is None:
        start_date = (pd.Timestamp.now().normalize() - pd.DateOffset(months=2)).strftime('%Y-%m-%d %H:%M:%S')
        end_date = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    else:
        start_date = pd.to_datetime(start_date).normalize().strftime('%Y-%m-%d %H:%M:%S')
        end_date = pd.to_datetime(end_date).normalize().strftime('%Y-%m-%d %H:%M:%S')

    query = text("""
        SELECT
          orders.id AS ORDERS,
          orders.created_at,
          restaurants.name AS `Restaurant name`,
          JSON_Extract(order_details.food_details, "$.name") AS product,
          order_details.price,
          order_details.quantity,
          orders.order_status,
          categories.name AS category,
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
                'Chernet',
                'Haregewyn'
              ) THEN 'Team 2'
            ELSE 'NO TEAM'
          END AS Team,
          CONCAT(admins.f_name, ' ', admins.l_name) AS bd_name
        FROM
          orders
          JOIN restaurants ON restaurants.id = orders.restaurant_id
          LEFT JOIN restaurant_fee_details fee ON fee.order_id = orders.id
          LEFT JOIN order_details ON order_details.order_id = orders.id
          LEFT JOIN categories ON categories.id = restaurants.category_id
          LEFT JOIN admins ON admins.id = restaurants.business_developer_id
        WHERE
          (
            orders.order_status = 'delivered'
            OR (
              orders.order_status = 'canceled'
              AND (
                orders.cancelation_reason IN ('R41', 'R42', 'R28')
                OR orders.cancelation_reason LIKE 'I%'
              )
            )
          )
          AND orders.created_at >= :start_date
          AND orders.created_at < :end_date
          AND restaurants.id NOT IN (999, 1329)
          AND restaurants.name NOT LIKE 'Ethio-post%'
        GROUP BY
          order_details.id
        ORDER BY
          orders.created_at ASC;
    """)

    with create_db_engine().connect() as connection:
      chunks = pd.read_sql(query, connection, params={"start_date": start_date, "end_date": end_date}, chunksize=50000)
      result = pd.concat(chunks, ignore_index=True) if chunks is not None else pd.DataFrame()

    if not result.empty:
      _safe_write_csv(result, SALES_CSV_PATH)

    return result


def fetch_data_all_cancellations(start_date: str | None = None, end_date: str | None = None):
    # Use full datetimes (current date + time) so we include up-to-the-second records.
    if end_date is None:
        end_date = pd.Timestamp.now()
    else:
        end_date = pd.to_datetime(end_date)

    if start_date is None:
        start_date = end_date - pd.DateOffset(months=2)
    else:
        start_date = pd.to_datetime(start_date)

    # Fixed Indentation here
    query = text("""
        SELECT
          orders.id,
          DATE_FORMAT(orders.created_at, '%Y-%m-%d %H:%i:%s') AS created_at,
          res.name AS restaurant_name,
          JSON_UNQUOTE(JSON_EXTRACT(or_detail.food_details, "$.name")) AS product,
          or_detail.price AS unit_price,
          or_detail.quantity,
          orders.delivery_charge,
          orders.order_amount,
          can_reason.message AS cancellation_reason,
          orders.order_status,
          CONCAT(admins.f_name, ' ', admins.l_name) AS BD,
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
                  'Chernet',
                  'Haregewyn'
                ) THEN 'Team 2'
              ELSE 'NO TEAM'
            END AS Team,
          (TIMESTAMPDIFF(SECOND, orders.placed_at, orders.canceled) / 60) AS cancel_time,
          categories.name AS category
        FROM
          orders
          JOIN restaurants res ON res.id = orders.restaurant_id
          JOIN order_details or_detail ON or_detail.order_id = orders.id
          LEFT JOIN cancellation_reasons can_reason ON can_reason.id = orders.cancelation_reason
          LEFT JOIN categories ON categories.id = res.category_id            -- Changed to LEFT JOIN
          LEFT JOIN admins ON admins.id = res.business_developer_id          -- Changed to LEFT JOIN
          LEFT JOIN food ON or_detail.food_id = food.id
        WHERE
          orders.created_at BETWEEN :start_date AND :end_date
          AND orders.order_status = 'canceled'
          AND orders.restaurant_id NOT IN (999, 1329)
          -- REMOVED the strict cancellation reason filter to fetch ALL canceled orders
          AND (
           can_reason.message LIKE '(Restaurant)%'
            OR orders.cancelation_reason IN ('C5', 'C2', 'C7', 'C8', 'R15')
         )
        GROUP BY
          or_detail.id
        ORDER BY
          orders.id ASC;
    """)

    with create_db_engine().connect() as connection:
        chunks = pd.read_sql(
            query,
            connection,
            params={
                "start_date": start_date.strftime('%Y-%m-%d %H:%M:%S'),
                "end_date": end_date.strftime('%Y-%m-%d %H:%M:%S'),
            },
            chunksize=50000,
        )
        # Handle generator output from chunksize safely
        result = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()

    if not result.empty:
        _safe_write_csv(result, CANCELLATIONS_CSV_PATH)

    return result


def fetch_data_all_delivered(start_date: str | None = None, end_date: str | None = None):
    # Use full datetimes (current date + time) so delivered fetches include up-to-now records.
    if end_date is None:
        end_date = pd.Timestamp.now()
    else:
        end_date = pd.to_datetime(end_date)

    if start_date is None:
      start_date = end_date - pd.DateOffset(months=2)
    else:
      start_date = pd.to_datetime(start_date)

    if _supports_item_columns():
        query = text("""
            SELECT
              orders.id AS ORDERS,
              restaurants.name AS `Restaurant name`,
              DATE_FORMAT(orders.created_at, '%Y-%m-%d %H:%i:%s') AS created_at,
                    IF(
                      order_status = 'delivered',
                      IF(
                        orders.coupon_discount_amount = 0 AND coupon_code IS NOT NULL,
                        orders.original_delivery_charge,
                        orders.coupon_discount_amount
                      ),
                      0
                    )
                   AS coupon_discount,
              restaurant_fee_details.restaurant_discount,
              restaurant_fee_details.restaurant_discount_on_food,
              restaurant_fee_details.beu_discount,
              restaurant_fee_details.beu_discount_on_food,
              restaurant_fee_details.restaurant_fee,
              restaurant_fee_details.commission_value,
              IF(categories.name IS NOT NULL, categories.name, 'null') AS Categories_Name,
              CONCAT(admins.f_name, ' ', admins.l_name) AS `BD NAME`,
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
                    'Chernet',
                    'Haregewyn'
                  ) THEN 'Team 2'
                ELSE 'NO TEAM'
              END AS Team,
              COALESCE(GROUP_CONCAT(DISTINCT menu_items.name ORDER BY menu_items.name SEPARATOR ', '), '') AS item_names
            FROM
              orders
              JOIN restaurants ON restaurants.id = orders.restaurant_id
              JOIN restaurant_fee_details ON restaurant_fee_details.order_id = orders.id
              LEFT JOIN categories ON restaurants.category_id = categories.id
              JOIN admins ON admins.id = restaurants.business_developer_id
              LEFT JOIN order_items ON order_items.order_id = orders.id
              LEFT JOIN menu_items ON menu_items.id = order_items.menu_item_id
            WHERE
              orders.created_at BETWEEN :start_date AND :end_date
              AND restaurants.name NOT LIKE 'Ethio-post%'
              AND restaurants.id NOT IN (999, 1329)
              AND orders.order_status = 'delivered'
            GROUP BY
              orders.id,
              restaurants.name,
              orders.created_at,
              orders.coupon_discount_amount,
              restaurant_fee_details.restaurant_discount,
              restaurant_fee_details.restaurant_discount_on_food,
              restaurant_fee_details.beu_discount,
              restaurant_fee_details.beu_discount_on_food,
              restaurant_fee_details.restaurant_fee,
              restaurant_fee_details.commission_value,
              categories.name,
              admins.f_name,
              admins.l_name
            ORDER BY orders.created_at ASC;
        """)
    else:
        query = text("""
            SELECT
              orders.id AS ORDERS,
              restaurants.name AS `Restaurant name`,
              DATE_FORMAT(orders.created_at, '%Y-%m-%d %H:%i:%s') AS created_at,
              orders.coupon_discount_amount,
              restaurant_fee_details.restaurant_discount,
              restaurant_fee_details.restaurant_discount_on_food,
              restaurant_fee_details.beu_discount,
              restaurant_fee_details.beu_discount_on_food,
              restaurant_fee_details.restaurant_fee,
              restaurant_fee_details.commission_value,
              IF(categories.name IS NOT NULL, categories.name, 'null') AS Categories_Name,
              CONCAT(admins.f_name, ' ', admins.l_name) AS `BD NAME`,
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
                    'Chernet',
                    'Haregewyn'
                  ) THEN 'Team 2'
                ELSE 'NO TEAM'
              END AS Team,
              '' AS item_names
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
      chunks = pd.read_sql(
        query,
        connection,
        params={
          "start_date": start_date.strftime('%Y-%m-%d %H:%M:%S'),
          "end_date": end_date.strftime('%Y-%m-%d %H:%M:%S'),
        },
        chunksize=50000,
      )
      result = pd.concat(chunks, ignore_index=True) if chunks is not None else pd.DataFrame()

    if not result.empty:
      _safe_write_csv(result, CSV_PATH)

    return result

def fetch_marketing_budgets(start_date: str | None = None, end_date: str | None = None):


    # Use full datetimes (current date + time) so we include up-to-the-second records.
    if end_date is None:
      end_date = pd.Timestamp.now()
    else:
      end_date = pd.to_datetime(end_date)

    if start_date is None:
      start_date = end_date - pd.DateOffset(months=2)
    else:
      start_date = pd.to_datetime(start_date)

      query = text("""
                  SELECT
              CONCAT(MIN(DATE(orders.created_at)), " - ", MAX(DATE(orders.created_at))) AS date_range,
              SUM(
                IF(
                  order_status = 'delivered',
                  IF(
                    orders.coupon_discount_amount = 0 AND coupon_code IS NOT NULL,
                    orders.original_delivery_charge,
                    orders.coupon_discount_amount
                  ),
                  0
                )
              ) AS coupon_discount,

              -- 2. Standard Aggregations
              sum(rfd.beu_discount
                  + rfd.beu_discount_on_food) as beu_discount,
              SUM(IF(wt.transaction_type LIKE '%debit%', wt.debit, 0)) AS wallet_used,
              SUM(orders.streak_discount_amount) AS streak_discount,
              SUM(orders.tier_discount_amount) AS tier_discount,
              -- 3. POS Discount
              SUM(IF(orders.created_by = 471, orders.pos_discount_amount, 0)) AS pos_discount,

              -- 4. Fixed JSON Delivery Charge logic (Added unique aliases and commas)
              SUM(IF(orders.log_details ->> '$.delivery_charges.free_delivery' = '1', orders.original_delivery_charge, 0)) AS free_delivery_Res,
              SUM(IF(orders.log_details ->> '$.delivery_charges.free_delivery' = '2', orders.original_delivery_charge, 0)) AS free_delivery_Coupoun,
              -- SUM(IF(orders.log_details ->> '$.delivery_charges.free_delivery' = '3', orders.original_delivery_charge, 0)) AS free_delivery_Driver,
              -- SUM(IF(orders.log_details ->> '$.delivery_charges.free_delivery' = '4', orders.original_delivery_charge, 0)) AS free_delivery_Refferal,
              SUM(IF(orders.log_details ->> '$.delivery_charges.free_delivery' = '5', orders.original_delivery_charge, 0)) AS free_delivery_tier,
              SUM(IF(orders.log_details ->> '$.delivery_charges.free_delivery' = '6', orders.original_delivery_charge, 0)) AS free_delivery_streak
              -- SUM(IF(orders.log_details ->> '$.delivery_charges.free_delivery' = '7', orders.original_delivery_charge, 0)) AS free_delivery_order_takeaway,
              -- SUM(IF(orders.log_details ->> '$.delivery_charges.free_delivery' = '8', orders.original_delivery_charge, 0)) AS free_delivery_Pos

            FROM orders
            JOIN restaurant_fee_details rfd ON rfd.order_id = orders.id
            LEFT JOIN wallet_transactions wt ON wt.order_id = orders.id
            WHERE DATE(orders.created_at) BETWEEN :start_date AND :end_date
              and orders.order_status = "delivered";
                """)

      with create_db_engine().connect() as connection:
        df = pd.read_sql(
            query,
            connection,
            params={
                "start_date": start_date.strftime('%Y-%m-%d %H:%M:%S'),
                "end_date": end_date.strftime('%Y-%m-%d %H:%M:%S'),
            }
        )
        return df

def _safe_write_csv(df: pd.DataFrame, path: str) -> str:
    """Write CSV safely: atomic replace via temp file, fallback to timestamped file on PermissionError.

    Returns the path written to (may be original path or fallback path).
    """
    logging.basicConfig()
    dirpath = os.path.dirname(path) or "."
    try:
      # create temp file in same dir to allow atomic replace across filesystems
      with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, dir=dirpath, suffix=".csv", newline="") as tmp:
        tmp_name = tmp.name
        df.to_csv(tmp_name, index=False, encoding="utf-8")
      # attempt atomic replace
      try:
        os.replace(tmp_name, path)
        return path
      except PermissionError:
        # target locked; fallback
        ts_path = f"{path}.csv"
        try:
          os.replace(tmp_name, ts_path)
          logging.warning(f"Could not replace {path}; wrote fallback {ts_path}")
          return ts_path
        except Exception as e:  # final fallback: write directly without replace
          logging.warning(f"Fallback replace failed: {e}; attempting direct write to {ts_path}")
          df.to_csv(ts_path, index=False, encoding="utf-8")
          return ts_path
    except PermissionError as e:
      # can't write temp file in dir (OneDrive lock or permissions) — write to temp dir instead
      tmpdir = tempfile.gettempdir()
      ts_path = os.path.join(tmpdir, f"{os.path.basename(path)}.{int(time.time())}.csv")
      df.to_csv(ts_path, index=False, encoding="utf-8")
      logging.warning(f"PermissionError writing to {path}; wrote to {ts_path} instead: {e}")
      return ts_path
    except Exception as e:
      logging.error(f"Unexpected error writing CSV to {path}: {e}")
      raise

def fetch_All_delivered(start_date: str | None = None, end_date: str | None = None):
    query = f"""
                    SELECT
                        orders.id, res.name as 'restaurant name', orders.created_at, orders.order_amount,
                        orders.coupon_discount_amount, orders.restaurant_discount_amount, orders.delivery_charge,
                        rfd.total_price, rfd.quantity, rfd.restaurant_discount, rfd.restaurant_discount_on_food,
                        rfd.beu_discount, rfd.beu_discount_on_food, rfd.price_after_restaurant_discount,
                        rfd.restaurant_fee, rfd.commission_value, ca.name as `resturant category`,
                        orders.order_status, orders.cancelation_reason, orders.service_charge,
                        orders.log_details->>'$.service_charges.restaurant_service_charge_amount' as resturant_service_charge,
                        res.comission, users.id AS user_id, users.app_language, users.phone, u_dz.name as user_district,
                        orders.created_by, orders.language_pref_fee,
                        orders.delivery_address ->> '$.dz_name' AS customer_district,
                        orders.delivery_address ->> '$.address' AS customer_addresses,
                        dz.name AS restaurant_district, CONCAT(admins.f_name, ' ', admins.l_name) AS `BD NAME`,
                        CASE
                            WHEN admins.f_name IN ('Yohannes', 'Abreham', 'Rekik', 'Yeabtsega') THEN 'Team 1'
                            WHEN admins.f_name IN ('Mifta', 'Abel', 'Cherenet', 'Haregewyn') THEN 'Team 2'
                            ELSE 'NO TEAM'
                        END AS Team
                    FROM orders
                    JOIN users ON users.id = orders.user_id
                    JOIN restaurants res ON res.id = orders.restaurant_id
                    LEFT JOIN categories ca ON ca.id = res.category_id
                    JOIN restaurant_fee_details rfd ON rfd.order_id = orders.id
                    JOIN delivery_zones dz ON dz.id = res.z_id
                    JOIN delivery_zones u_dz ON u_dz.id=users.z_id
                    JOIN admins ON admins.id = res.business_developer_id
                    WHERE DATE(orders.created_at) BETWEEN '{start_date}' AND '{end_date}'
                    AND orders.order_status = 'delivered';
                    """
    with create_db_engine().connect() as connection:
        chunks = pd.read_sql(query, connection, chunksize=50000)
        result = pd.concat(chunks, ignore_index=True) if chunks is not None else pd.DataFrame()
        return result

def fetch_All_Canclation(start_date: str | None = None, end_date: str | None = None):
    query = f"""
                SELECT
                    orders.id, res.name as `Rest_Name`, orders.created_at, orders.order_amount,
                    orders.coupon_discount_amount, orders.restaurant_discount_amount, orders.delivery_charge,
                    rfd.total_price, rfd.quantity, rfd.restaurant_discount, rfd.restaurant_discount_on_food,
                    rfd.beu_discount, rfd.beu_discount_on_food, rfd.price_after_restaurant_discount, rfd.restaurant_fee,
                    orders.log_details->>'$.service_charges.restaurant_service_charge_amount' as resturant_service_charge,
                    rfd.commission_value, orders.order_status, orders.cancelation_reason, ca.message as `cancelation_reasons`,
                    orders.service_charge, res.comission, users.id AS user_id, users.app_language, users.phone,
                    u_dz.name as user_district, orders.created_by, orders.language_pref_fee,
                    orders.delivery_address ->> '$.dz_name' AS customer_district,
                    orders.delivery_address ->> '$.address' AS customer_addresses,
                    dz.name AS restaurant_district, CONCAT(admins.f_name, ' ', admins.l_name) AS `BD NAME`,
                    CASE
                        WHEN admins.f_name IN ('Yohannes', 'Abreham', 'Rekik', 'Yeabtsega') THEN 'Team 1'
                        WHEN admins.f_name IN ('Mifta', 'Abel', 'Cherenet', 'Haregewyn') THEN 'Team 2'
                        ELSE 'NO TEAM'
                    END AS Team
                FROM orders
                JOIN users ON users.id = orders.user_id
                JOIN restaurants res ON res.id = orders.restaurant_id
                LEFT JOIN cancellation_reasons ca ON ca.id=orders.cancelation_reason
                LEFT JOIN restaurant_fee_details rfd ON rfd.order_id = orders.id
                JOIN delivery_zones dz ON dz.id = res.z_id
                JOIN admins ON admins.id = res.business_developer_id
                JOIN delivery_zones u_dz ON u_dz.id=users.z_id
                WHERE DATE(orders.created_at) BETWEEN '{start_date}' AND '{end_date}'
                AND orders.order_status = 'canceled';
                """
    with create_db_engine().connect() as connection:
        chunks = pd.read_sql(query, connection, chunksize=50000)
        result = pd.concat(chunks, ignore_index=True) if chunks is not None else pd.DataFrame()
        return result
def fetch_root_file():
        query = f"""
                SELECT
                    r.id, r.name as res_name, r.status, r.is_deleted, r.comission, r.service_charge,
                    r.upFrontPayment, r.phone, r.optional_phone_numbers, r.opening_time, r.closeing_time,
                    r.break_start_time, r.break_end_time, r.off_day, r.free_delivery, r.address,
                    categories.name as categorie_name, CONCAT(admins.f_name, ' ', admins.l_name) AS `BD NAME`,
                    CASE
                        WHEN admins.f_name IN ('Yohannes', 'Abreham', 'Rekik', 'Yeabtsega') THEN 'Team 1'
                        WHEN admins.f_name IN ('Mifta', 'Abel', 'Cherenet', 'Haregewyn') THEN 'Team 2'
                        ELSE 'NO TEAM'
                    END AS Team,
                    dz.name as District,
                    count(distinct if(food.status = 1, food.id, null)) active,
                    count(distinct if(food.status = 0, food.id, null)) inactive
                FROM restaurants r
                LEFT JOIN admins ON admins.id = r.business_developer_id
                LEFT JOIN food ON food.restaurant_id = r.id
                LEFT JOIN delivery_zones dz ON dz.id = r.z_id
                LEFT JOIN categories ON categories.id = r.category_id
                WHERE r.is_deleted != 1
                AND r.name not like 'Ethio-post%'
                AND food.deleted_at IS NULL
                GROUP BY r.id;
                """
        with create_db_engine().connect() as connection:
            chunks = pd.read_sql(query, connection, chunksize=50000)
            result = pd.concat(chunks, ignore_index=True) if chunks is not None else pd.DataFrame()
        return result
def fetch_restaurant_payment(start_date: str | None = None, end_date: str | None = None):
    query = """
               select od.id                                                                                     as order_details_id,
       o.id                                                                                      as order_id,
       f.name                                                                                    as item_name,
       r.name                                                                                    as restaurant_name,
       od.price,
       od.total_add_on_price,
       od.quantity,
       ((od.price * od.quantity)+od.total_add_on_price) as total_amount,
       (
    ((od.price * od.quantity) + od.total_add_on_price)
    - (((od.price * od.quantity) * od.rest_rest_discount) / 100)
    - CASE
        WHEN od.food_discount_type = 'amount' THEN od.food_rest_discount * od.quantity
        ELSE (((od.price * od.quantity) * od.food_rest_discount) / 100)
      END
) AS price_after_res_discount,
   (  (((od.price * od.quantity) * od.rest_rest_discount) / 100)
    + CASE
        WHEN od.food_discount_type = 'amount' THEN od.food_rest_discount * od.quantity
        ELSE (((od.price * od.quantity) * od.food_rest_discount) / 100)
      END) as restaurant_discount,

   (
  (
    (
  (
    ((od.price * od.quantity) + od.total_add_on_price)
    - (((od.price * od.quantity) * od.rest_rest_discount) / 100)
    - CASE
        WHEN od.food_discount_type = 'amount' THEN od.food_rest_discount * od.quantity
        ELSE (((od.price * od.quantity) * od.food_rest_discount) / 100)
      END
)
  ) * rfd.commission_percentage
) / 100) AS commission_amount,
       (
  (
    ((od.price * od.quantity) + od.total_add_on_price)
    - (((od.price * od.quantity) * od.rest_rest_discount) / 100)
    - CASE
        WHEN od.food_discount_type = 'amount' THEN od.food_rest_discount * od.quantity
        ELSE (((od.price * od.quantity) * od.food_rest_discount) / 100)
      END
) - (
  (
    (
      (
        ((od.price * od.quantity) + od.total_add_on_price) - (
          ((od.price * od.quantity) * od.rest_rest_discount) / 100
        ) - CASE
          WHEN od.food_discount_type = 'amount' THEN od.food_rest_discount * od.quantity
          ELSE (
            ((od.price * od.quantity) * od.food_rest_discount) / 100
          )
        END
      )
    ) * rfd.commission_percentage
  ) / 100
)
) AS restaurant_fee
from orders o
         join beu.order_details od on o.id = od.order_id
         join food f on od.food_id = f.id
         join beu.restaurants r on o.restaurant_id = r.id
         join restaurant_fee_details rfd on o.id = rfd.order_id
where r.id not in (999, 1329)
  and r.name not like 'Ethio-post%'
  and r.name not like '%Donate%'
  and date(o.created_at) between %s and %s

 
  and (
    o.order_status = 'delivered'
        or (
        o.order_status = 'canceled' and (
            o.cancelation_reason in ('R41', 'R42', 'R28')
                or o.cancelation_reason like 'I%')
        )
    )
                """
    with create_db_engine().connect() as connection:
        chunks = pd.read_sql(query, connection,params=(start_date, end_date), chunksize=50000)
        result = pd.concat(chunks, ignore_index=True) if chunks is not None else pd.DataFrame()
        return result
def fetch_restaurant_order_count_in_each_district(start_date: str | None = None, end_date: str | None = None):
    query = """
             select
    date(o.created_at) as order_date,
    r.name as restaurant_name,
        dz.name as district,
        concat(a.f_name,' ',a.l_name) as `Bd name`,
        count(distinct o.id) as order_count


    from orders o
join beu.restaurants r on o.restaurant_id = r.id
join delivery_zones dz on dz.id=r.z_id
join beu.admins a on r.business_developer_id = a.id
        where
date(o.created_at) between %s and %s
  and r.id not in (999, 1329)
and (
    o.order_status = 'delivered'
    or (
      o.order_status = 'canceled' and (
      o.cancelation_reason in ('R41', 'R42', 'R28')
      or o.cancelation_reason like 'I%' )
    )
  )
group by o.restaurant_id,date(o.created_at);
                """
    with create_db_engine().connect() as connection:
        chunks = pd.read_sql(query, connection,params=(start_date, end_date), chunksize=50000)
        result = pd.concat(chunks, ignore_index=True) if chunks is not None else pd.DataFrame()
        return result