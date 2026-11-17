select
    f.*,
    p.primer_mes,
    p.meses_con_dato,
    p.petroleo_12m_m3,
    p.gas_12m_miles_m3,
    case when f.etapas < 20 then '01-19'
         when f.etapas < 40 then '20-39'
         when f.etapas < 60 then '40-59'
         else '60+' end      as rango_etapas,
    p.meses_con_dato = 12    as anio_completo
from {{ ref('fractura_por_pozo') }} as f
inner join {{ ref('produccion_primer_anio') }} as p on p.idpozo = f.idpozo