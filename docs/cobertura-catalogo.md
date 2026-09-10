# Cobertura del catálogo

Qué vista de [ETL-SIEEJ](https://github.com/iieg-oficial/ETL-SIEEJ) alimenta a qué indicador, y
**qué vistas quedaron fuera y por qué**. Se revisaron las **182 vistas vigentes** de los **35 pipelines** que definen alguna,
leídas de `migrations/<pipeline>/sql/`. De ellas, **57 alimentan 120 indicadores**.

> La fuente de verdad son las migraciones, no los README de pipeline. Tanto este documento como
> los YAML de las vistas listadas abajo se generan desde `scripts/curaduria_vistas.py` con
> `python scripts/generar_catalogo.py`. Si una vista cambia en ETL-SIEEJ, se ajusta la curaduría
> y se regenera; no se editan los YAML a mano.

## Qué entró

| Pipeline | Vista | Indicadores |
| --- | --- | --- |
| `agropecuario_siap` | `vm_agricola_geo` | 5 |
| `asg_imss` | `brecha_salarial` | 3 |
| `asg_imss` | `trabajadores_asegurados` | 4 |
| `conapo` | `edad_mediana` | 1 |
| `conapo` | `poblacion_hombres` | 1 |
| `conapo` | `poblacion_mujeres` | 1 |
| `conapo` | `porcentaje_poblacional_municipal_en_entidad` | 1 |
| `conapo` | `razon_dependencia` | 1 |
| `conapo` | `razon_dependencia_adulta` | 1 |
| `conapo` | `razon_dependencia_infantil` | 1 |
| `delitos_fuero_comun` | `vwm_datos_delitos_abuso_sexual_secretariado` | 2 |
| `delitos_fuero_comun` | `vwm_datos_delitos_feminicidio_secretariado` | 2 |
| `delitos_fuero_comun` | `vwm_datos_delitos_homicidio_doloso_secretariado` | 2 |
| `delitos_fuero_comun` | `vwm_datos_delitos_lesiones_dolosas_secretariado` | 2 |
| `delitos_fuero_comun` | `vwm_datos_delitos_robo_autopartes_secretariado` | 2 |
| `delitos_fuero_comun` | `vwm_datos_delitos_robo_casa_habitacion_secretariado` | 2 |
| `delitos_fuero_comun` | `vwm_datos_delitos_robo_coche_cuatro_ruedas_secretariado` | 2 |
| `delitos_fuero_comun` | `vwm_datos_delitos_robo_institucion_bancaria_secretariado` | 2 |
| `delitos_fuero_comun` | `vwm_datos_delitos_robo_motocicleta_secretariado` | 2 |
| `delitos_fuero_comun` | `vwm_datos_delitos_robo_negocio_secretariado` | 2 |
| `delitos_fuero_comun` | `vwm_datos_delitos_robo_transeunte_via_publica_secretariado` | 2 |
| `delitos_fuero_comun` | `vwm_datos_delitos_robo_transportista_secretariado` | 2 |
| `delitos_fuero_comun` | `vwm_datos_delitos_violacion_secretariado` | 2 |
| `delitos_fuero_comun` | `vwm_datos_delitos_violencia_familiar_secretariado` | 2 |
| `delitos_fuero_comun` | `vwm_datos_delitos_violencia_genero_no_familiar_secretariado` | 2 |
| `efipem` | `egresos_deuda_publica` | 1 |
| `efipem` | `egresos_totales` | 1 |
| `efipem` | `ingresos_financiamiento` | 1 |
| `efipem` | `ingresos_participaciones` | 1 |
| `efipem` | `ingresos_totales` | 1 |
| `efipem` | `ingresos_totales_reales_precios_2023` | 1 |
| `indice_shf_vivienda` | `vw_indice_shf_vivienda_estatal` | 1 |
| `indice_shf_vivienda` | `vw_indice_shf_vivienda_municipal` | 1 |
| `inpc` | `v_inpc_entidades` | 1 |
| `inpc` | `v_inpc_nacional` | 1 |
| `intensidad_migratoria` | `vm_iim_geo` | 5 |
| `marginacion` | `vm_marginacion_geo` | 9 |
| `nacimientos_dgis` | `tasa_fecundidad` | 3 |
| `pobreza_multidimensional` | `carencia_acceso_alimentacion` | 2 |
| `pobreza_multidimensional` | `carencia_acceso_seguridad_social` | 2 |
| `pobreza_multidimensional` | `carencia_acceso_servicios_salud` | 2 |
| `pobreza_multidimensional` | `carencia_calidad_espacios_vivienda` | 2 |
| `pobreza_multidimensional` | `carencia_servicios_basicos_vivienda` | 2 |
| `pobreza_multidimensional` | `no_pobre_y_no_vulnerable` | 2 |
| `pobreza_multidimensional` | `poblacion_con_al_menos_una_carencia_social` | 2 |
| `pobreza_multidimensional` | `poblacion_con_tres_o_mas_carencias_sociales` | 2 |
| `pobreza_multidimensional` | `poblacion_ingreso_inferior_linea_pobreza_extrema_ingresos` | 2 |
| `pobreza_multidimensional` | `poblacion_ingreso_inferior_linea_pobreza_ingresos` | 2 |
| `pobreza_multidimensional` | `pobreza` | 3 |
| `pobreza_multidimensional` | `pobreza_extrema` | 3 |
| `pobreza_multidimensional` | `pobreza_moderada` | 3 |
| `pobreza_multidimensional` | `rezago_educativo` | 2 |
| `pobreza_multidimensional` | `vulnerables_por_carencia_social` | 2 |
| `pobreza_multidimensional` | `vulnerables_por_ingreso` | 2 |
| `produccion_ganadera` | `vm_prod_pecuaria_geo` | 1 |
| `repd` | `personas_desaparecidas` | 4 |
| `repd` | `personas_localizadas` | 4 |

## Qué quedó fuera

Ninguna de estas vistas es un error: simplemente no son una serie de `(geografía, periodo, valor)`,
que es lo único que el formato largo sabe servir. Ver [contrato-salida.md](contrato-salida.md).

| Motivo | Qué significa |
| --- | --- |
| `microdatos` | Microdatos: un renglon por persona o por caso, no una serie por geografia y periodo. |
| `directorio` | Directorio o padron: un renglon por establecimiento, escuela o unidad; no tiene serie temporal. |
| `puntual` | Eventos georreferenciados punto a punto; se consume como capa GIS, no como serie. |
| `sin_clave` | Es una serie municipal pero la vista no proyecta `clave_municipio`: no se puede formar `cve_geo`. |
| `sin_geo` | No expone una clave geografica utilizable (solo el nombre del municipio o de la entidad). |
| `requiere_agregacion` | El grano es mas fino que (geografia, periodo, categoria); necesitaria GROUP BY para entrar al formato largo. |
| `catalogo` | Catalogo o jerarquia de referencia, sin mediciones. |
| `insumo` | Vista intermedia, insumo de otra vista o de un producto editorial. |
| `piloto` | Ya cubierta por un indicador curado a mano del catalogo piloto. |
| `redundante` | Redundante: sus columnas ya se publican desde otra vista del mismo pipeline. |

| Pipeline | Vista | Motivo |
| --- | --- | --- |
| `agropecuario_siap` | `view_agricola_jalisco` | `requiere_agregacion` |
| `asg_imss` | `trabajadores_asegurados_hombres` | `redundante` |
| `asg_imss` | `trabajadores_asegurados_mujeres` | `redundante` |
| `asg_imss` | `vw_asg_imss` | `requiere_agregacion` |
| `censo_poblacion` | `view_inegi_2010` | `requiere_agregacion` |
| `censo_poblacion` | `view_inegi_2015` | `requiere_agregacion` |
| `censo_poblacion` | `view_inegi_2020` | `requiere_agregacion` |
| `censos_economicos` | `vw_economico_estatal_2019` | `requiere_agregacion` |
| `censos_economicos` | `vw_economico_estatal_2024` | `requiere_agregacion` |
| `censos_economicos` | `vw_economico_municipal_2019` | `requiere_agregacion` |
| `censos_economicos` | `vw_economico_municipal_2024` | `requiere_agregacion` |
| `censos_economicos` | `vw_economico_nacional_2019` | `requiere_agregacion` |
| `censos_economicos` | `vw_economico_nacional_2024` | `requiere_agregacion` |
| `centros_educativos` | `v_centros_educativos` | `directorio` |
| `conapo` | `poblacion` | `sin_clave` |
| `conapo` | `view_grandes_grupos_edad` | `requiere_agregacion` |
| `conapo` | `view_indicadores_demograficos` | `requiere_agregacion` |
| `conapo` | `view_poblacion_mitad_anio` | `requiere_agregacion` |
| `datamexico` | `v_flujo_comercio` | `requiere_agregacion` |
| `defunciones` | `vw_defunciones` | `microdatos` |
| `defunciones` | `vw_defunciones_municipio` | `requiere_agregacion` |
| `defunciones` | `vw_defunciones_principales_causas` | `requiere_agregacion` |
| `defunciones` | `vw_mortalidad_infantil` | `requiere_agregacion` |
| `defunciones` | `vw_mortalidad_materna` | `requiere_agregacion` |
| `defunciones_inegi` | `vw_defunciones` | `microdatos` |
| `defunciones_inegi` | `vw_defunciones_ampliacion` | `microdatos` |
| `defunciones_inegi` | `vw_defunciones_ampliacion_jalisco` | `microdatos` |
| `defunciones_inegi` | `vw_defunciones_jalisco` | `microdatos` |
| `delitos_fuero_comun` | `vw_delitos_comparables_general` | `piloto` |
| `delitos_fuero_comun` | `vw_delitos_serie_historica` | `piloto` |
| `delitos_fuero_comun` | `vw_extorsion` | `piloto` |
| `delitos_fuero_comun` | `vw_feminicidio` | `piloto` |
| `delitos_fuero_comun` | `vw_gold_delitos_fuero_comun` | `requiere_agregacion` |
| `delitos_fuero_comun` | `vw_homicidio_doloso` | `piloto` |
| `delitos_fuero_comun` | `vw_narcomenudeo` | `piloto` |
| `delitos_fuero_comun` | `vw_otros_fuero_comun` | `piloto` |
| `delitos_fuero_comun` | `vw_otros_libertad_personal` | `piloto` |
| `delitos_fuero_comun` | `vw_otros_libertad_sexual` | `piloto` |
| `delitos_fuero_comun` | `vw_otros_patrimonio` | `piloto` |
| `delitos_fuero_comun` | `vw_otros_sociedad` | `piloto` |
| `delitos_fuero_comun` | `vw_otros_vida_integridad` | `piloto` |
| `delitos_fuero_comun` | `vw_servidores_publicos` | `piloto` |
| `delitos_fuero_comun` | `vw_tentativa_extorsion` | `piloto` |
| `delitos_fuero_comun` | `vw_tentativa_feminicidio` | `piloto` |
| `delitos_fuero_comun` | `vw_tentativa_homicidio_doloso` | `piloto` |
| `delitos_fuero_comun` | `vw_trata_personas` | `piloto` |
| `delitos_fuero_comun` | `vwm_feminicidios` | `redundante` |
| `denue` | `v_establecimientos` | `requiere_agregacion` |
| `denue` | `v_establecimientos_jalisco` | `directorio` |
| `edafologia` | `vw_cuadernillos_edafologia_cobertura_municipal` | `insumo` |
| `edafologia` | `vw_cuadernillos_edafologia_estadistica_detalle` | `insumo` |
| `edafologia` | `vw_cuadernillos_edafologia_estadistica_resumen` | `insumo` |
| `edafologia` | `vw_cuadernillos_edafologia_variables_texto` | `insumo` |
| `edafologia` | `vw_edafologia_resumenes_municipales` | `insumo` |
| `efipem` | `ingresos_totales_reales_per_capita_precios_2023` | `sin_clave` |
| `efipem` | `porcentaje_egresos_deuda_publica` | `sin_clave` |
| `efipem` | `porcentaje_ingresos_financiamiento` | `sin_clave` |
| `efipem` | `porcentaje_ingresos_participaciones` | `sin_clave` |
| `efipem` | `porcentaje_ingresos_propios` | `sin_clave` |
| `efipem` | `vw_efipem` | `requiere_agregacion` |
| `emec` | `vw_emec` | `requiere_agregacion` |
| `emec` | `vw_emec_jalisco` | `requiere_agregacion` |
| `emim` | `vw_emim` | `requiere_agregacion` |
| `emim` | `vw_emim_jalisco` | `requiere_agregacion` |
| `ems` | `vw_ems` | `requiere_agregacion` |
| `ems` | `vw_ems_jalisco` | `requiere_agregacion` |
| `enec` | `vw_enec_entidad` | `requiere_agregacion` |
| `enec` | `vw_enec_jalisco` | `requiere_agregacion` |
| `enec` | `vw_enec_nacional` | `requiere_agregacion` |
| `enoe` | `v_enoe_indicadores_municipio` | `sin_geo` |
| `enoe` | `v_enoe_jalisco` | `microdatos` |
| `enoe_microdatos` | `mv_enoe_microdatos` | `microdatos` |
| `enoe_microdatos` | `mv_enoe_tasas` | `sin_geo` |
| `enoe_microdatos` | `mv_enoe_tasas_jalisco` | `piloto` |
| `escuelas` | `v_directorio_escuelas` | `directorio` |
| `escuelas` | `v_estadistica_escuelas` | `sin_geo` |
| `establecimientos_de_salud` | `v_establecimientos` | `directorio` |
| `establecimientos_de_salud` | `v_establecimientos_activos_jalisco` | `directorio` |
| `establecimientos_de_salud` | `v_establecimientos_jalisco` | `directorio` |
| `etef` | `v_etef` | `requiere_agregacion` |
| `fiscalia` | `delitos_fiscalia_abuso_sexual_infantil` | `puntual` |
| `fiscalia` | `delitos_fiscalia_feminicidio` | `puntual` |
| `fiscalia` | `delitos_fiscalia_homicidio_doloso` | `puntual` |
| `fiscalia` | `delitos_fiscalia_lesiones_dolosas` | `puntual` |
| `fiscalia` | `delitos_fiscalia_robo_autopartes` | `puntual` |
| `fiscalia` | `delitos_fiscalia_robo_bancos` | `puntual` |
| `fiscalia` | `delitos_fiscalia_robo_carga_pesada` | `puntual` |
| `fiscalia` | `delitos_fiscalia_robo_casa_habitacion` | `puntual` |
| `fiscalia` | `delitos_fiscalia_robo_cuentahabientes` | `puntual` |
| `fiscalia` | `delitos_fiscalia_robo_int_vehiculos` | `puntual` |
| `fiscalia` | `delitos_fiscalia_robo_motocicleta` | `puntual` |
| `fiscalia` | `delitos_fiscalia_robo_negocio` | `puntual` |
| `fiscalia` | `delitos_fiscalia_robo_persona` | `puntual` |
| `fiscalia` | `delitos_fiscalia_robo_vehiculos_particulares` | `puntual` |
| `fiscalia` | `delitos_fiscalia_violacion` | `puntual` |
| `fiscalia` | `delitos_fiscalia_violencia_familiar` | `puntual` |
| `fiscalia` | `vw_mapalab_fiscalia` | `puntual` |
| `ilmm` | `vw_ilmm` | `requiere_agregacion` |
| `ilmm` | `vw_ocupacion_informal` | `piloto` |
| `ilmm` | `vw_tasa_desocupacion` | `piloto` |
| `indice_shf_vivienda` | `vw_indice_shf_vivienda_global` | `sin_geo` |
| `indice_shf_vivienda` | `vw_indice_shf_vivienda_jalisco` | `redundante` |
| `inpc` | `v_inpc_ciudades` | `sin_geo` |
| `intensidad_migratoria` | `view_iim_entidades` | `requiere_agregacion` |
| `intensidad_migratoria` | `view_iim_municipios_jalisco_2010` | `sin_geo` |
| `intensidad_migratoria` | `view_iim_municipios_jalisco_2020` | `sin_geo` |
| `marginacion` | `view_marginacion_estatal` | `sin_geo` |
| `marginacion` | `view_marginacion_localidades` | `sin_geo` |
| `marginacion` | `view_marginacion_municipal` | `sin_geo` |
| `nacimientos_dgis` | `nacimientos_adolescentes` | `sin_clave` |
| `nacimientos_dgis` | `nacimientos_infantiles` | `sin_clave` |
| `nacimientos_dgis` | `vw_nacimientos` | `requiere_agregacion` |
| `nacimientos_dgis` | `vw_nacimientos_adolescentes` | `sin_geo` |
| `nacimientos_dgis` | `vw_tasa_fecundidad` | `sin_geo` |
| `participacion_ciudadana` | `vw_participacion` | `sin_geo` |
| `pobreza_multidimensional` | `vw_pobreza_multidimencional` | `piloto` |
| `produccion_ganadera` | `view_ganadera_jalisco` | `requiere_agregacion` |
| `rastros` | `vw_rastros` | `requiere_agregacion` |
| `rastros` | `vw_rastros_jalisco` | `requiere_agregacion` |
| `repd` | `personas_desaparecidas_hombres` | `redundante` |
| `repd` | `personas_desaparecidas_mujeres` | `redundante` |
| `repd` | `personas_localizadas_hombres` | `redundante` |
| `repd` | `personas_localizadas_mujeres` | `redundante` |
| `repd` | `vw_repd` | `microdatos` |
| `scian` | `view_scian_estructura` | `catalogo` |

## Hallazgo: ocho vistas municipales sin `clave_municipio`

Estas vistas materializadas son series municipales —una fila por municipio y por año— pero su
`SELECT` proyecta `clave_entidad` y **no** `clave_municipio`. El municipio solo queda identificado
por su nombre, así que no se puede formar una `cve_geo` de 5 dígitos ni cruzarlas con nada.

- `conapo` · `poblacion`
- `efipem` · `ingresos_totales_reales_per_capita_precios_2023`
- `efipem` · `porcentaje_egresos_deuda_publica`
- `efipem` · `porcentaje_ingresos_financiamiento`
- `efipem` · `porcentaje_ingresos_participaciones`
- `efipem` · `porcentaje_ingresos_propios`
- `nacimientos_dgis` · `nacimientos_adolescentes`
- `nacimientos_dgis` · `nacimientos_infantiles`

Se arregla aguas arriba, en ETL-SIEEJ: agregar `LPAD(cvegeo::text, 5, '0') AS clave_municipio`
al `SELECT` de cada una, igual que hacen sus vistas hermanas del mismo pipeline. En cuanto
estén, entran al catálogo sin más trabajo que regenerarlo.

## Coberturas temporales por confirmar

Los indicadores cuyo `cobertura.temporal` dice `por confirmar contra la base` se generaron sin
acceso a las bases: la migración no declara el rango y no se inventó uno. Se cierran corriendo
las pruebas de integración contra el servidor — ver [pruebas-integracion.md](pruebas-integracion.md).

---

Cómo se escribe un YAML: [anatomia-yaml.md](anatomia-yaml.md).
El catálogo con el que arrancó el proyecto: [catalogo-piloto.md](catalogo-piloto.md).
