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
          CONCAT(admins.f_name, '-', admins.l_name) AS bd_name
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
            WHEN admins.f_name IN ('Yeabtsega', 'Yohannes','Rekik','Abreham') THEN 'Team 1'
            WHEN admins.f_name IN ('Mifta','Chernet', 'Abel','Haregewyn') THEN 'Team 2'
            ELSE 'NO TEAM'
          END AS team,
          (TIMESTAMPDIFF(SECOND, orders.placed_at, orders.canceled) / 60) AS cancel_time,
          categories.name AS category
        FROM
          orders
          JOIN restaurants res ON res.id = orders.restaurant_id
          JOIN order_details or_detail ON or_detail.order_id = orders.id
          LEFT JOIN cancellation_reasons can_reason ON can_reason.id = orders.cancelation_reason
          JOIN categories ON categories.id = res.category_id
          JOIN admins ON admins.id = res.business_developer_id
          LEFT JOIN food ON or_detail.food_id = food.id
        WHERE
          orders.created_at BETWEEN :start_date AND :end_date
          AND orders.order_status = 'canceled'
          AND orders.restaurant_id NOT IN (999, 1329)
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
      result = pd.concat(chunks, ignore_index=True) if chunks is not None else pd.DataFrame()

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
        ts_path = f"{path}.{int(time.time())}.csv"
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