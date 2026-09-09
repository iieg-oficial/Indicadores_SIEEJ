# -*- coding: utf-8 -*-
"""Tabla de curaduria: que vista de ETL-SIEEJ es una serie de indicador y como leerla.

La consume scripts/generar_catalogo.py. Agregar una vista aqui y regenerar es
equivalente a escribir sus YAML a mano, pero sin desviarse del molde.
"""

MUN = dict(nivel="municipal", geo_col="clave_municipio", nombre_col="nombre", fecha_col="fecha")
GEOMV = dict(nivel="municipal", geo_col="cvegeo", nombre_col="municipio", fecha_col="fecha")

# --- pobreza -----------------------------------------------------------------
CONEVAL = dict(
    pipeline="pobreza_multidimensional",
    tema="pobreza",
    fuente="CONEVAL - Medicion de la pobreza multidimensional municipal",
    periodicidad="quinquenal",
    periodo="anual",
    cobertura_geo="Municipios de Jalisco",
    cobertura_tmp="2010, 2015, 2020",
    notas=(
        "Los tres cortes usan metodologias distintas del CONEVAL: la serie no es estrictamente "
        "comparable ano contra ano."
    ),
    **MUN,
)

POBREZA = [
    (
        "pobreza",
        "Poblacion en situacion de pobreza",
        "Personas con al menos una carencia social y un ingreso inferior a la linea de pobreza por ingresos.",
    ),
    (
        "pobreza_extrema",
        "Poblacion en pobreza extrema",
        "Personas con ingreso inferior a la linea de pobreza extrema y tres o mas carencias sociales.",
    ),
    (
        "pobreza_moderada",
        "Poblacion en pobreza moderada",
        "Personas en situacion de pobreza que no estan en pobreza extrema.",
    ),
    (
        "vulnerables_por_carencia_social",
        "Poblacion vulnerable por carencias sociales",
        "Personas con al menos una carencia social pero con ingreso superior a la linea de pobreza por ingresos.",
    ),
    (
        "vulnerables_por_ingreso",
        "Poblacion vulnerable por ingresos",
        "Personas sin carencias sociales pero con ingreso inferior a la linea de pobreza por ingresos.",
    ),
    (
        "no_pobre_y_no_vulnerable",
        "Poblacion no pobre y no vulnerable",
        "Personas sin carencias sociales y con ingreso superior a la linea de pobreza por ingresos.",
    ),
    ("rezago_educativo", "Carencia por rezago educativo", "Personas con carencia por rezago educativo."),
    (
        "carencia_acceso_servicios_salud",
        "Carencia por acceso a servicios de salud",
        "Personas con carencia por acceso a servicios de salud.",
    ),
    (
        "carencia_acceso_seguridad_social",
        "Carencia por acceso a la seguridad social",
        "Personas con carencia por acceso a la seguridad social.",
    ),
    (
        "carencia_calidad_espacios_vivienda",
        "Carencia por calidad y espacios de la vivienda",
        "Personas con carencia por calidad y espacios de la vivienda.",
    ),
    (
        "carencia_servicios_basicos_vivienda",
        "Carencia por servicios basicos en la vivienda",
        "Personas con carencia por acceso a servicios basicos en la vivienda.",
    ),
    (
        "carencia_acceso_alimentacion",
        "Carencia por acceso a la alimentacion",
        "Personas con carencia por acceso a la alimentacion nutritiva y de calidad.",
    ),
    (
        "poblacion_con_al_menos_una_carencia_social",
        "Poblacion con al menos una carencia social",
        "Personas con al menos una de las seis carencias sociales que mide el CONEVAL.",
    ),
    (
        "poblacion_con_tres_o_mas_carencias_sociales",
        "Poblacion con tres o mas carencias sociales",
        "Personas con tres o mas de las seis carencias sociales que mide el CONEVAL.",
    ),
    (
        "poblacion_ingreso_inferior_linea_pobreza_ingresos",
        "Poblacion con ingreso inferior a la linea de pobreza",
        "Personas cuyo ingreso es inferior a la linea de pobreza por ingresos.",
    ),
    (
        "poblacion_ingreso_inferior_linea_pobreza_extrema_ingresos",
        "Poblacion con ingreso inferior a la linea de pobreza extrema",
        "Personas cuyo ingreso es inferior a la linea de pobreza extrema por ingresos.",
    ),
]

VISTAS = []

for vista, titulo, definicion in POBREZA:
    medidas = [
        dict(
            id=f"{vista}_porcentaje",
            nombre=f"{titulo}, porcentaje",
            col="porcentaje",
            unidad="porcentaje",
            definicion=f"{definicion} Expresado como porcentaje de la poblacion municipal.",
        ),
        dict(
            id=f"{vista}_personas",
            nombre=f"{titulo}, personas",
            col="personas",
            unidad="personas",
            definicion=f"{definicion} Expresado en numero de personas.",
        ),
    ]
    if vista in ("pobreza", "pobreza_extrema", "pobreza_moderada"):
        medidas.append(
            dict(
                id=f"{vista}_carencias_promedio",
                nombre=f"{titulo}, carencias promedio",
                col="carencias_promedio",
                unidad="carencias por persona",
                definicion=f"Numero promedio de carencias sociales de la poblacion en esta condicion. {definicion}",
            )
        )
    VISTAS.append(dict(CONEVAL, origen=vista, medidas=medidas))

# --- poblacion (CONAPO) ------------------------------------------------------
CONAPO = dict(
    pipeline="conapo",
    tema="poblacion",
    fuente="CONAPO - Proyecciones de la poblacion de los municipios de Mexico",
    periodicidad="anual",
    periodo="anual",
    cobertura_geo="Municipios de Jalisco",
    cobertura_tmp="por confirmar contra la base",
    notas=(
        "Son proyecciones demograficas, no conteos censales: los anos posteriores al ultimo "
        "censo son estimaciones de CONAPO."
    ),
    **MUN,
)

for vista, titulo, unidad, definicion in [
    (
        "poblacion_hombres",
        "Poblacion masculina",
        "personas",
        "Poblacion masculina proyectada a mitad de ano por municipio.",
    ),
    (
        "poblacion_mujeres",
        "Poblacion femenina",
        "personas",
        "Poblacion femenina proyectada a mitad de ano por municipio.",
    ),
    (
        "edad_mediana",
        "Edad mediana",
        "anios",
        "Edad que divide a la poblacion del municipio en dos mitades de igual tamano.",
    ),
    (
        "porcentaje_poblacional_municipal_en_entidad",
        "Peso demografico del municipio en Jalisco",
        "porcentaje",
        "Porcentaje que representa la poblacion del municipio respecto al total de Jalisco.",
    ),
    (
        "razon_dependencia",
        "Razon de dependencia total",
        "dependientes por cada 100 personas en edad activa",
        "Poblacion menor de 15 anos y de 65 o mas por cada 100 personas de 15 a 64 anos.",
    ),
    (
        "razon_dependencia_adulta",
        "Razon de dependencia adulta",
        "dependientes por cada 100 personas en edad activa",
        "Poblacion de 65 anos o mas por cada 100 personas de 15 a 64 anos.",
    ),
    (
        "razon_dependencia_infantil",
        "Razon de dependencia infantil",
        "dependientes por cada 100 personas en edad activa",
        "Poblacion menor de 15 anos por cada 100 personas de 15 a 64 anos.",
    ),
]:
    VISTAS.append(
        dict(
            CONAPO,
            origen=vista,
            medidas=[dict(id=vista, nombre=titulo, col="valor", unidad=unidad, definicion=definicion)],
        )
    )

# --- finanzas publicas (EFIPEM) ---------------------------------------------
EFIPEM = dict(
    pipeline="efipem",
    tema="finanzas_publicas",
    fuente="INEGI - Estadistica de Finanzas Publicas Estatales y Municipales (EFIPEM)",
    periodicidad="anual",
    periodo="anual",
    cobertura_geo="Municipios de Jalisco",
    cobertura_tmp="1990-2024",
    notas=(
        "La vista es un grid completo municipio x ano: los municipios sin dato reportado ese ano "
        "aparecen con valor nulo, no ausentes."
    ),
    **MUN,
)

for vista, titulo, unidad, definicion in [
    (
        "ingresos_totales",
        "Ingresos municipales totales",
        "pesos corrientes",
        "Suma de los ingresos brutos recaudados por el municipio en el ano, a precios corrientes.",
    ),
    (
        "egresos_totales",
        "Egresos municipales totales",
        "pesos corrientes",
        "Suma de los egresos brutos ejercidos por el municipio en el ano, a precios corrientes.",
    ),
    (
        "ingresos_participaciones",
        "Participaciones federales",
        "pesos corrientes",
        "Monto de participaciones federales recibidas por el municipio en el ano.",
    ),
    (
        "ingresos_financiamiento",
        "Ingresos por financiamiento",
        "pesos corrientes",
        "Ingresos por financiamiento o deuda publica contratada por el municipio en el ano.",
    ),
    (
        "egresos_deuda_publica",
        "Egresos por deuda publica",
        "pesos corrientes",
        "Pago de deuda publica del municipio en el ano: amortizacion de capital mas intereses.",
    ),
    (
        "ingresos_totales_reales_precios_2023",
        "Ingresos municipales totales reales",
        "pesos constantes de 2023",
        "Ingresos municipales totales deflactados con el INPC a precios constantes de 2023.",
    ),
]:
    VISTAS.append(
        dict(
            EFIPEM,
            origen=vista,
            medidas=[dict(id=vista, nombre=titulo, col="valor", unidad=unidad, definicion=definicion)],
        )
    )

# --- seguridad: incidencia delictiva del Secretariado ------------------------
SESNSP = dict(
    pipeline="delitos_fuero_comun",
    tema="seguridad",
    fuente="SESNSP - Incidencia delictiva del fuero comun, nueva metodologia",
    periodicidad="mensual",
    periodo="mensual",
    cobertura_geo="Municipios de Jalisco",
    cobertura_tmp="2015 a la fecha",
    notas=(
        "Carpetas de investigacion abiertas, no victimas ni delitos. La tasa usa como denominador "
        "la proyeccion de poblacion de CONAPO del ano correspondiente."
    ),
    **MUN,
)

DELITOS = [
    ("abuso_sexual", "Abuso sexual", True),
    ("feminicidio", "Feminicidio", False),
    ("homicidio_doloso", "Homicidio doloso", False),
    ("lesiones_dolosas", "Lesiones dolosas", False),
    ("robo_autopartes", "Robo de autopartes", False),
    ("robo_casa_habitacion", "Robo a casa habitacion", False),
    ("robo_coche_cuatro_ruedas", "Robo de coche de cuatro ruedas", False),
    ("robo_institucion_bancaria", "Robo a institucion bancaria", False),
    ("robo_motocicleta", "Robo de motocicleta", False),
    ("robo_negocio", "Robo a negocio", False),
    ("robo_transeunte_via_publica", "Robo a transeunte en via publica", False),
    ("robo_transportista", "Robo a transportista", False),
    ("violacion", "Violacion", True),
    ("violencia_familiar", "Violencia familiar", True),
    ("violencia_genero_no_familiar", "Violencia de genero en el ambito no familiar", True),
]

for corto, titulo, con_modalidad in DELITOS:
    v = dict(SESNSP, origen=f"vwm_datos_delitos_{corto}_secretariado")
    if con_modalidad:
        v["categoria_col"] = "modalidad"
    v["medidas"] = [
        dict(
            id=f"{corto}_carpetas",
            nombre=f"{titulo}, carpetas de investigacion",
            col="carpetas_investigacion",
            unidad="carpetas de investigacion",
            definicion=f"Carpetas de investigacion abiertas por {titulo.lower()} en el municipio durante el mes.",
        ),
        dict(
            id=f"{corto}_tasa",
            nombre=f"{titulo}, tasa por 100 mil habitantes",
            col="tasa_carpetas_investigacion",
            unidad="carpetas por cada 100 mil habitantes",
            definicion=f"Carpetas de investigacion por {titulo.lower()} por cada 100 mil habitantes del municipio.",
        ),
    ]
    VISTAS.append(v)

# --- seguridad: personas desaparecidas y localizadas (REPD) ------------------
REPD = dict(
    pipeline="repd",
    tema="seguridad",
    fuente="Registro Estatal de Personas Desaparecidas (REPD), Fiscalia del Estado de Jalisco",
    periodicidad="mensual",
    periodo="mensual",
    cobertura_geo="Municipios de Jalisco",
    cobertura_tmp="por confirmar contra la base",
    notas=(
        "El municipio es el de desaparicion, no el de residencia. Las tasas usan como denominador "
        "la poblacion de CONAPO del ano correspondiente."
    ),
    **MUN,
)

VISTAS.append(
    dict(
        REPD,
        origen="personas_desaparecidas",
        medidas=[
            dict(
                id="personas_desaparecidas_total",
                nombre="Personas desaparecidas",
                col="total",
                unidad="personas",
                definicion="Personas reportadas como desaparecidas en el municipio durante el mes.",
            ),
            dict(
                id="personas_desaparecidas_hombres",
                nombre="Hombres desaparecidos",
                col="total_hombres",
                unidad="personas",
                definicion="Hombres reportados como desaparecidos en el municipio durante el mes.",
            ),
            dict(
                id="personas_desaparecidas_mujeres",
                nombre="Mujeres desaparecidas",
                col="total_mujeres",
                unidad="personas",
                definicion="Mujeres reportadas como desaparecidas en el municipio durante el mes.",
            ),
            dict(
                id="personas_desaparecidas_tasa",
                nombre="Personas desaparecidas, tasa por 100 mil habitantes",
                col="tasa_total",
                unidad="personas por cada 100 mil habitantes",
                definicion="Personas desaparecidas por cada 100 mil habitantes del municipio.",
            ),
        ],
    )
)

VISTAS.append(
    dict(
        REPD,
        origen="personas_localizadas",
        medidas=[
            dict(
                id="personas_localizadas_total",
                nombre="Personas localizadas",
                col="total",
                unidad="personas",
                definicion="Personas localizadas en el municipio durante el mes.",
            ),
            dict(
                id="personas_localizadas_con_vida",
                nombre="Personas localizadas con vida",
                col="con_vida",
                unidad="personas",
                definicion="Personas localizadas con vida en el municipio durante el mes.",
            ),
            dict(
                id="personas_localizadas_sin_vida",
                nombre="Personas localizadas sin vida",
                col="sin_vida",
                unidad="personas",
                definicion="Personas localizadas sin vida en el municipio durante el mes.",
            ),
            dict(
                id="personas_localizadas_tasa",
                nombre="Personas localizadas, tasa por 100 mil habitantes",
                col="tasa_total",
                unidad="personas por cada 100 mil habitantes",
                definicion="Personas localizadas por cada 100 mil habitantes del municipio.",
            ),
        ],
    )
)

# --- empleo: puestos de trabajo afiliados al IMSS ----------------------------
IMSS = dict(
    pipeline="asg_imss",
    tema="empleo",
    fuente="IMSS - Asegurados en el IMSS (ASG), puestos de trabajo afiliados",
    periodicidad="mensual",
    periodo="mensual",
    cobertura_geo="Municipios de Jalisco",
    cobertura_tmp="por confirmar contra la base",
    notas=(
        "Mide puestos de trabajo afiliados, no personas: quien tiene dos empleos formales cuenta "
        "dos veces. Solo cubre el empleo formal afiliado al IMSS."
    ),
    **MUN,
)

VISTAS.append(
    dict(
        IMSS,
        origen="trabajadores_asegurados",
        medidas=[
            dict(
                id="trabajadores_asegurados_total",
                nombre="Puestos de trabajo afiliados al IMSS",
                col="total",
                unidad="puestos de trabajo",
                definicion="Puestos de trabajo afiliados al IMSS en el municipio al corte del mes.",
            ),
            dict(
                id="trabajadores_asegurados_hombres",
                nombre="Puestos de trabajo afiliados al IMSS, hombres",
                col="total_hombres",
                unidad="puestos de trabajo",
                definicion="Puestos de trabajo afiliados al IMSS ocupados por hombres en el municipio al corte del mes.",
            ),
            dict(
                id="trabajadores_asegurados_mujeres",
                nombre="Puestos de trabajo afiliados al IMSS, mujeres",
                col="total_mujeres",
                unidad="puestos de trabajo",
                definicion="Puestos de trabajo afiliados al IMSS ocupados por mujeres en el municipio al corte del mes.",
            ),
            dict(
                id="trabajadores_asegurados_porcentaje_mujeres",
                nombre="Participacion de mujeres en el empleo formal",
                col="porcentaje_mujeres",
                unidad="porcentaje",
                definicion="Porcentaje de los puestos de trabajo afiliados al IMSS del municipio ocupados por mujeres.",
            ),
        ],
    )
)

VISTAS.append(
    dict(
        IMSS,
        origen="brecha_salarial",
        medidas=[
            dict(
                id="brecha_salarial",
                nombre="Brecha salarial entre hombres y mujeres",
                col="brecha_salarial",
                unidad="porcentaje",
                definicion=(
                    "Diferencia porcentual entre el salario promedio diario de hombres y el de mujeres, "
                    "respecto al de los hombres. Un valor positivo indica que las mujeres ganan menos."
                ),
            ),
            dict(
                id="salario_promedio_diario_mujeres",
                nombre="Salario promedio diario de las mujeres",
                col="salario_promedio_diario_mujeres",
                unidad="pesos por dia",
                definicion="Masa salarial de las mujeres entre sus puestos con salario registrado en el IMSS.",
            ),
            dict(
                id="salario_promedio_diario_hombres",
                nombre="Salario promedio diario de los hombres",
                col="salario_promedio_diario_hombres",
                unidad="pesos por dia",
                definicion="Masa salarial de los hombres entre sus puestos con salario registrado en el IMSS.",
            ),
        ],
    )
)

# --- economia: produccion agropecuaria (SIAP) --------------------------------
VISTAS.append(
    dict(
        pipeline="agropecuario_siap",
        tema="economia",
        fuente="SIAP - Cierre de la produccion agricola municipal",
        periodicidad="anual",
        periodo="anual",
        cobertura_geo="Municipios de Jalisco",
        cobertura_tmp="por confirmar contra la base",
        notas="Agrega todos los cultivos, ciclos y modalidades del municipio en el ano.",
        origen="vm_agricola_geo",
        **GEOMV,
        medidas=[
            dict(
                id="valor_produccion_agricola",
                nombre="Valor de la produccion agricola",
                col="valor_produccion_total_mdp",
                unidad="millones de pesos",
                definicion="Valor total de la produccion agricola del municipio en el ano.",
            ),
            dict(
                id="superficie_sembrada",
                nombre="Superficie sembrada",
                col="superficie_sembrada_total_ha",
                unidad="hectareas",
                definicion="Superficie total sembrada en el municipio en el ano.",
            ),
            dict(
                id="superficie_cosechada",
                nombre="Superficie cosechada",
                col="superficie_cosechada_total_ha",
                unidad="hectareas",
                definicion="Superficie total cosechada en el municipio en el ano.",
            ),
            dict(
                id="superficie_siniestrada",
                nombre="Superficie siniestrada",
                col="superficie_siniestrada_total_ha",
                unidad="hectareas",
                definicion="Superficie sembrada que se perdio por siniestro en el municipio en el ano.",
            ),
            dict(
                id="volumen_produccion_agricola",
                nombre="Volumen de la produccion agricola",
                col="volumen_produccion_total_toneladas",
                unidad="toneladas",
                definicion="Volumen total de la produccion agricola del municipio en el ano.",
            ),
        ],
    )
)

VISTAS.append(
    dict(
        pipeline="produccion_ganadera",
        tema="economia",
        fuente="SIAP - Cierre de la produccion pecuaria municipal",
        periodicidad="anual",
        periodo="anual",
        cobertura_geo="Municipios de Jalisco",
        cobertura_tmp="por confirmar contra la base",
        notas="Agrega todas las especies y productos pecuarios del municipio en el ano.",
        origen="vm_prod_pecuaria_geo",
        **GEOMV,
        medidas=[
            dict(
                id="valor_produccion_pecuaria",
                nombre="Valor de la produccion pecuaria",
                col="valor_produccion_total_mdp",
                unidad="millones de pesos",
                definicion="Valor total de la produccion pecuaria del municipio en el ano.",
            ),
        ],
    )
)

# --- economia: precios y vivienda -------------------------------------------
VISTAS.append(
    dict(
        pipeline="inpc",
        tema="economia",
        fuente="INEGI - Indice Nacional de Precios al Consumidor (INPC)",
        periodicidad="mensual",
        periodo="mensual",
        nivel="nacional",
        nombre_col="'Nacional'",
        fecha_col="fecha",
        cobertura_geo="Nacional",
        cobertura_tmp="por confirmar contra la base",
        categoria_col="objeto_gasto",
        notas="La columna categoria trae el objeto del gasto; el indice general viene en su propia categoria.",
        origen="v_inpc_nacional",
        medidas=[
            dict(
                id="inpc_nacional",
                nombre="Indice Nacional de Precios al Consumidor",
                col="indice_de_precios",
                unidad="indice",
                definicion="Indice nacional de precios al consumidor por objeto del gasto.",
            )
        ],
    )
)

VISTAS.append(
    dict(
        pipeline="inpc",
        tema="economia",
        fuente="INEGI - Indice Nacional de Precios al Consumidor (INPC)",
        periodicidad="mensual",
        periodo="mensual",
        nivel="estatal",
        geo_col="cve_ent",
        nombre_col="entidad",
        fecha_col="fecha",
        cobertura_geo="Entidades federativas",
        cobertura_tmp="por confirmar contra la base",
        categoria_col="objeto_gasto",
        notas="La columna categoria trae el objeto del gasto; el indice general viene en su propia categoria.",
        origen="v_inpc_entidades",
        medidas=[
            dict(
                id="inpc_estatal",
                nombre="INPC por entidad federativa",
                col="indice_de_precios",
                unidad="indice",
                definicion="Indice de precios al consumidor por entidad federativa y objeto del gasto.",
            )
        ],
    )
)

SHF = dict(
    pipeline="indice_shf_vivienda",
    tema="economia",
    fuente="SHF - Indice SHF de precios de la vivienda en Mexico",
    periodicidad="trimestral",
    periodo="trimestral",
    periodo_expr="anio::text || '-Q' || trimestre::text",
    anio_expr="anio",
    cobertura_tmp="por confirmar contra la base",
    fecha_col="fecha",
    notas="SHF solo publica los municipios con mercado hipotecario suficiente, no los 125 de Jalisco.",
)

VISTAS.append(
    dict(
        SHF,
        origen="vw_indice_shf_vivienda_estatal",
        nivel="estatal",
        geo_col="entidad_id",
        nombre_col="nom_ent",
        cobertura_geo="Entidades federativas",
        medidas=[
            dict(
                id="indice_shf_vivienda_estatal",
                nombre="Indice SHF de precios de la vivienda, estatal",
                col="indice",
                unidad="indice",
                definicion="Indice SHF de precios de la vivienda por entidad federativa.",
            )
        ],
    )
)

VISTAS.append(
    dict(
        SHF,
        origen="vw_indice_shf_vivienda_municipal",
        nivel="municipal",
        geo_col="municipio_id",
        nombre_col="nomgeo",
        cobertura_geo="Municipios que publica SHF",
        medidas=[
            dict(
                id="indice_shf_vivienda_municipal",
                nombre="Indice SHF de precios de la vivienda, municipal",
                col="indice",
                unidad="indice",
                definicion="Indice SHF de precios de la vivienda por municipio.",
            )
        ],
    )
)

# --- desarrollo social -------------------------------------------------------
VISTAS.append(
    dict(
        pipeline="intensidad_migratoria",
        tema="desarrollo_social",
        fuente="CONAPO - Indice de intensidad migratoria Mexico-Estados Unidos",
        periodicidad="decenal",
        periodo="anual",
        cobertura_geo="Municipios de Jalisco",
        cobertura_tmp="por confirmar contra la base",
        notas=(
            "El grado de intensidad migratoria es una categoría de texto y por eso no llega al banco; "
            "aqui van solo sus componentes numericos."
        ),
        origen="vm_iim_geo",
        **GEOMV,
        medidas=[
            dict(
                id="viviendas_totales_iim",
                nombre="Viviendas totales del municipio",
                col="total_viviendas",
                unidad="viviendas",
                definicion="Total de viviendas del municipio usado como denominador del indice.",
            ),
            dict(
                id="viviendas_con_remesas",
                nombre="Viviendas que reciben remesas",
                col="porcentaje_viviendas_remesas",
                unidad="porcentaje",
                definicion="Porcentaje de viviendas del municipio que reciben remesas.",
            ),
            dict(
                id="viviendas_con_emigrantes",
                nombre="Viviendas con emigrantes a Estados Unidos",
                col="porcentaje_viviendas_emigrantes",
                unidad="porcentaje",
                definicion="Porcentaje de viviendas del municipio con emigrantes a Estados Unidos en el quinquenio.",
            ),
            dict(
                id="viviendas_con_migrantes_circulares",
                nombre="Viviendas con migrantes circulares",
                col="porcentaje_viviendas_migrantes_circulares",
                unidad="porcentaje",
                definicion="Porcentaje de viviendas del municipio con migrantes circulares.",
            ),
            dict(
                id="viviendas_con_migrantes_de_retorno",
                nombre="Viviendas con migrantes de retorno",
                col="porcentaje_viviendas_migrantes_de_retorno",
                unidad="porcentaje",
                definicion="Porcentaje de viviendas del municipio con migrantes de retorno.",
            ),
        ],
    )
)

VISTAS.append(
    dict(
        pipeline="marginacion",
        tema="desarrollo_social",
        fuente="CONAPO - Indice de marginacion por municipio",
        periodicidad="quinquenal",
        periodo="anual",
        cobertura_geo="Municipios de Jalisco",
        cobertura_tmp="por confirmar contra la base",
        notas=(
            "El grado de marginacion es una categoría de texto y por eso no llega al banco; aqui van "
            "solo los indicadores que lo componen."
        ),
        origen="vm_marginacion_geo",
        **GEOMV,
        medidas=[
            dict(
                id="poblacion_analfabeta",
                nombre="Poblacion de 15 anos o mas analfabeta",
                col="porcentaje_poblacion_15mas_analfabeta",
                unidad="porcentaje",
                definicion="Porcentaje de la poblacion de 15 anos o mas que no sabe leer ni escribir.",
            ),
            dict(
                id="poblacion_sin_educacion_basica",
                nombre="Poblacion de 15 anos o mas sin educacion basica",
                col="porcentaje_poblacion_15mas_sin_educacion_basica",
                unidad="porcentaje",
                definicion="Porcentaje de la poblacion de 15 anos o mas sin educacion basica completa.",
            ),
            dict(
                id="viviendas_sin_drenaje",
                nombre="Ocupantes en viviendas sin drenaje ni excusado",
                col="porcentaje_ocupantes_vivienda_sin_drenaje_ni_excusado",
                unidad="porcentaje",
                definicion="Porcentaje de ocupantes en viviendas sin drenaje ni excusado.",
            ),
            dict(
                id="viviendas_sin_electricidad",
                nombre="Ocupantes en viviendas sin electricidad",
                col="porcentaje_ocupantes_vivienda_sin_electricidad",
                unidad="porcentaje",
                definicion="Porcentaje de ocupantes en viviendas sin energia electrica.",
            ),
            dict(
                id="viviendas_sin_agua_entubada",
                nombre="Ocupantes en viviendas sin agua entubada",
                col="porcentaje_ocupantes_vivienda_sin_agua_entubada",
                unidad="porcentaje",
                definicion="Porcentaje de ocupantes en viviendas sin agua entubada.",
            ),
            dict(
                id="viviendas_con_piso_de_tierra",
                nombre="Ocupantes en viviendas con piso de tierra",
                col="porcentaje_ocupantes_vivienda_piso_tierra",
                unidad="porcentaje",
                definicion="Porcentaje de ocupantes en viviendas con piso de tierra.",
            ),
            dict(
                id="viviendas_con_hacinamiento",
                nombre="Viviendas con hacinamiento",
                col="porcentaje_viviendas_hacinamiento",
                unidad="porcentaje",
                definicion="Porcentaje de viviendas del municipio con algun nivel de hacinamiento.",
            ),
            dict(
                id="poblacion_en_localidades_pequenas",
                nombre="Poblacion en localidades de menos de 5 mil habitantes",
                col="porcentaje_poblacion_localidades_menos_5k_habitantes",
                unidad="porcentaje",
                definicion="Porcentaje de la poblacion que vive en localidades de menos de 5 mil habitantes.",
            ),
            dict(
                id="poblacion_hasta_dos_salarios_minimos",
                nombre="Poblacion ocupada con ingreso de hasta dos salarios minimos",
                col="porcentaje_poblacion_ingresos_hasta_2_salarios_minimos",
                unidad="porcentaje",
                definicion="Porcentaje de la poblacion ocupada con ingreso de hasta dos salarios minimos.",
            ),
        ],
    )
)

# --- salud -------------------------------------------------------------------
VISTAS.append(
    dict(
        pipeline="nacimientos_dgis",
        tema="salud",
        fuente="DGIS, Secretaria de Salud - Nacimientos registrados",
        periodicidad="anual",
        periodo="anual",
        cobertura_geo="Municipios de Jalisco",
        cobertura_tmp="por confirmar contra la base",
        origen="tasa_fecundidad",
        **MUN,
        medidas=[
            dict(
                id="tasa_fecundidad_general",
                nombre="Tasa de fecundidad general",
                col="tasa_fecundidad_general",
                unidad="nacimientos por cada mil mujeres de 15 a 49 anos",
                definicion="Nacimientos por cada mil mujeres en edad fertil (15 a 49 anos) del municipio.",
            ),
            dict(
                id="nacimientos_registrados",
                nombre="Nacimientos registrados",
                col="nacimientos",
                unidad="nacimientos",
                definicion="Nacimientos registrados en el municipio en el ano.",
            ),
            dict(
                id="mujeres_en_edad_fertil",
                nombre="Mujeres de 15 a 49 anos",
                col="poblacion_mujeres_15_49",
                unidad="personas",
                definicion="Mujeres de 15 a 49 anos del municipio, denominador de la tasa de fecundidad.",
            ),
        ],
    )
)
