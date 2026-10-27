select customer_id, region from {{ ref('customers') }} qualify row_number() over (partition by customer_id order by version desc) = 1
