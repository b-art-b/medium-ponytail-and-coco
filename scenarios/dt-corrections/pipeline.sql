-- Evaluator supplies the isolated database/schema and uses COMPUTE_WH.
CREATE DYNAMIC TABLE clean_orders
  TARGET_LAG = DOWNSTREAM WAREHOUSE = COMPUTE_WH
  REFRESH_MODE = INCREMENTAL INITIALIZE = ON_CREATE
AS SELECT order_id, order_day, region, gross_cents - COALESCE(refund_cents, 0) AS net_cents
FROM raw_orders;
CREATE DYNAMIC TABLE daily_sales
  TARGET_LAG = DOWNSTREAM WAREHOUSE = COMPUTE_WH
  REFRESH_MODE = INCREMENTAL INITIALIZE = ON_CREATE
AS SELECT order_day, SUM(gross_cents) AS net_cents
FROM raw_orders WHERE refund_cents = 0 GROUP BY order_day;
