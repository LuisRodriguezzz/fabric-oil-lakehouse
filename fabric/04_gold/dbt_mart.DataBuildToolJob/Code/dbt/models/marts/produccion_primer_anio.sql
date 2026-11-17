with inicio as (
    select idpozo, min(mes) as primer_mes
    from {{ ref('stg_produccion_pozo') }}
    where petroleo_m3 > 0 or gas_miles_m3 > 0
    group by idpozo
)
select
    p.idpozo,
    i.primer_mes,
    count(*)            as meses_con_dato,
    sum(p.petroleo_m3)  as petroleo_12m_m3,
    sum(p.gas_miles_m3) as gas_12m_miles_m3
from {{ ref('stg_produccion_pozo') }} as p
inner join inicio as i on i.idpozo = p.idpozo
where p.mes >= i.primer_mes
  and p.mes <  add_months(i.primer_mes, 12)
group by p.idpozo, i.primer_mes