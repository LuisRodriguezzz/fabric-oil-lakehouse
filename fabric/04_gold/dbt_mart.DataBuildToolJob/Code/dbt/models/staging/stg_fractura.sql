
select
    id_base_fractura_adjiv,
    idpozo,
    cuenca,
    formacion_productiva       as formacion,
    tipo_reservorio,
    empresa_informante         as empresa,
    fecha_inicio_fractura,
    cantidad_fracturas         as etapas,
    longitud_rama_horizontal_m as rama_horizontal_m,
    coalesce(arena_bombeada_nacional_tn, 0)
      + coalesce(arena_bombeada_importada_tn, 0) as arena_tn,
    agua_inyectada_m3          as agua_m3
from {{ source('energia', 'fractura') }}