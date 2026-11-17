select
    idpozo,
    max(cuenca)                as cuenca,
    max(formacion)             as formacion,
    max(tipo_reservorio)       as tipo_reservorio,
    max(empresa)               as empresa,
    min(fecha_inicio_fractura) as primera_fractura,
    count(*)                   as operaciones,
    sum(etapas)                as etapas,
    max(rama_horizontal_m)     as rama_horizontal_m,
    sum(arena_tn)              as arena_tn,
    sum(agua_m3)               as agua_m3
from {{ ref('stg_fractura') }}
group by idpozo
having sum(etapas) is not null