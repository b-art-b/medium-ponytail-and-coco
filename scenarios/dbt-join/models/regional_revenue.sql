select c.region, sum(o.gross_cents) as gross_cents
from {{ ref('stg_orders') }} o
join {{ ref('customers') }} c on o.customer_id = c.customer_id
group by c.region
