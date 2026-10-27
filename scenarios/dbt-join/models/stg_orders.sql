select order_id, customer_id, order_day::date as order_day, gross_cents::number(18,0) as gross_cents from {{ ref('orders') }}
