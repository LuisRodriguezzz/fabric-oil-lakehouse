select
    idpozo,
    make_date(anio, mes, 1) as mes,
    coalesce(prod_pet, 0)   as petroleo_m3,
    coalesce(prod_gas, 0)   as gas_miles_m3
from {{ source('energia', 'produccion_pozo') }}