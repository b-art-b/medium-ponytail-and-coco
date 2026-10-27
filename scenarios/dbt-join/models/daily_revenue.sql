select order_day, sum(gross_cents) as net_cents from {{ ref('stg_orders') }} group by order_day
