# -*- coding: utf-8 -*-
"""Regenera los YAML del catalogo a partir de la curaduria de vistas de ETL-SIEEJ.

    python scripts/generar_catalogo.py

Sobrescribe `catalogo/<tema>/<id>.yaml` para cada indicador declarado en
`curaduria_vistas.py`, que es donde se dice que vista de ETL-SIEEJ es una serie de
indicador, cual de sus columnas es el valor y con que unidad se lee. La fuente de
verdad de las vistas son las migraciones de ETL-SIEEJ, no sus README.

No toca los indicadores curados a mano que no esten en esa tabla.
"""

import re
from pathlib import Path
from textwrap import indent

DESTINO = Path(__file__).resolve().parents[1] / "catalogo"

# --- SQL ---------------------------------------------------------------------
# Un solo molde: proyecta las cinco columnas del formato largo y deja los tres
# filtros opcionales resueltos con (:param IS NULL OR condicion).

PERIODO = {
    "anual": "to_char({f}, 'YYYY')",
    "mensual": "to_char({f}, 'YYYY-MM')",
    "trimestral": "{f}",
}

GEO = {
    # (expresion cve_geo, expresion para comparar con :cve_geo)
    "municipal": "LPAD({c}::text, 5, '0')",
    "estatal": "LPAD({c}::text, 2, '0')",
    "nacional": "'00'",
}


def sql_de(v, m):
    geo = GEO[v["nivel"]].format(c=v.get("geo_col", ""))
    periodo = v.get("periodo_expr") or PERIODO[v["periodo"]].format(f=v.get("fecha_col", "fecha"))
    anio = v.get("anio_expr", "EXTRACT(YEAR FROM {f})".format(f=v.get("fecha_col", "fecha")))
    cat = v.get("categoria_col")
    categoria = f"{cat}::text" if cat else "NULL::text"

    filtros = [
        f"(CAST(:anio_min AS integer) IS NULL\n       OR {anio} >= CAST(:anio_min AS integer))",
        f"(CAST(:anio_max AS integer) IS NULL\n       OR {anio} <= CAST(:anio_max AS integer))",
    ]
    if v["nivel"] != "nacional":
        filtros.insert(0, f"(CAST(:cve_geo AS text) IS NULL\n       OR {geo} = CAST(:cve_geo AS text))")

    where = "\n  AND ".join(filtros)

    return (
        "SELECT\n"
        f"    {geo:<44} AS cve_geo,\n"
        f"    {v['nombre_col'] + '::text':<44} AS nombre_geo,\n"
        f"    {periodo:<44} AS periodo,\n"
        f"    {m['col'] + '::numeric':<44} AS valor,\n"
        f"    {categoria:<44} AS categoria\n"
        f"FROM {v['origen']}\n"
        f"WHERE {where}\n"
        "ORDER BY cve_geo, periodo"
    )


PARAMS = {
    "cve_geo_municipal": {
        "nombre": "cve_geo",
        "tipo": "str",
        "requerido": False,
        "descripcion": "Clave INEGI de 5 digitos del municipio (ej. 14039). Omitir para todos los municipios.",
    },
    "cve_geo_estatal": {
        "nombre": "cve_geo",
        "tipo": "str",
        "requerido": False,
        "descripcion": "Clave INEGI de 2 digitos de la entidad (ej. 14 para Jalisco). Omitir para todas.",
    },
    "anio_min": {
        "nombre": "anio_min",
        "tipo": "int",
        "requerido": False,
        "descripcion": "Primer anio de la serie, inclusive. Omitir para empezar en el primero disponible.",
    },
    "anio_max": {
        "nombre": "anio_max",
        "tipo": "int",
        "requerido": False,
        "descripcion": "Ultimo anio de la serie, inclusive. Omitir para llegar al ultimo disponible.",
    },
}


ACENTOS = {
    "Poblacion": "Población",
    "poblacion": "población",
    "situacion": "situación",
    "Medicion": "Medición",
    "linea": "línea",
    "Estadistica": "Estadística",
    "Publicas": "Públicas",
    "publica": "pública",
    "publicas": "públicas",
    "ano": "año",
    "anos": "años",
    "anio": "año",
    "anios": "años",
    "Numero": "Número",
    "numero": "número",
    "numericos": "numéricos",
    "Mexico": "México",
    "Indice": "Índice",
    "indice": "índice",
    "Marginacion": "Marginación",
    "marginacion": "marginación",
    "educacion": "educación",
    "basica": "básica",
    "electrica": "eléctrica",
    "energia": "energía",
    "minimos": "mínimos",
    "Fiscalia": "Fiscalía",
    "metodologia": "metodología",
    "metodologias": "metodologías",
    "investigacion": "investigación",
    "Violacion": "Violación",
    "genero": "género",
    "ambito": "ámbito",
    "via": "vía",
    "institucion": "institución",
    "transeunte": "transeúnte",
    "dia": "día",
    "dias": "días",
    "fertil": "fértil",
    "Secretaria": "Secretaría",
    "hectareas": "hectáreas",
    "produccion": "producción",
    "Produccion": "Producción",
    "agricola": "agrícola",
    "Agricola": "Agrícola",
    "demografico": "demográfico",
    "demograficas": "demográficas",
    "Razon": "Razón",
    "razon": "razón",
    "tamano": "tamaño",
    "proyeccion": "proyección",
    "comun": "común",
    "Participacion": "Participación",
    "ultimo": "último",
    "Ultimo": "Último",
    "digitos": "dígitos",
    "desaparicion": "desaparición",
    "amortizacion": "amortización",
    "perdio": "perdió",
    "pequenas": "pequeñas",
    "aqui": "aquí",
    "mas": "más",
    "algun": "algún",
    "algunos": "algunos",
    "condicion": "condición",
    "alimentacion": "alimentación",
    "Alimentacion": "Alimentación",
    "violacion": "violación",
    "estan": "están",
    "basicos": "básicos",
    "Basicos": "Básicos",
    "asi": "así",
}
_PALABRA = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")


def acentuar(texto):
    """Repone acentos en la prosa. Nunca toca identificadores: solo se llama sobre
    nombre, definicion, unidad, fuente, notas y las descripciones de parametros."""
    return _PALABRA.sub(lambda m: ACENTOS.get(m.group(0), m.group(0)), texto)


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def yaml_de(v, m):
    p = []
    if v["nivel"] != "nacional":
        p.append(PARAMS["cve_geo_" + v["nivel"]])
    p += [PARAMS["anio_min"], PARAMS["anio_max"]]

    out = [
        f"id: {m['id']}",
        f"nombre: {acentuar(m['nombre'])}",
        f"tema: {v['tema']}",
        "definicion: >",
        indent("\n".join(_wrap(acentuar(m["definicion"]))), "  "),
        f"unidad: {acentuar(m['unidad'])}",
        f"fuente: {acentuar(v['fuente'])}",
        f"pipeline: {v['pipeline']}",
        f"origen: {v['origen']}",
        f"nivel: {v['nivel']}",
        f"periodicidad: {v['periodicidad']}",
        "cobertura:",
        f"  geografica: {acentuar(v['cobertura_geo'])}",
        f'  temporal: "{v["cobertura_tmp"]}"',
    ]
    notas = m.get("notas") or v.get("notas")
    if notas:
        out += ["notas: |", indent("\n".join(_wrap(acentuar(notas))), "  ")]
    out.append("parametros:")
    for x in p:
        out += [
            f"  - nombre: {x['nombre']}",
            f"    tipo: {x['tipo']}",
            f"    requerido: {str(x['requerido']).lower()}",
            f"    descripcion: {acentuar(x['descripcion'])}",
        ]
    out += ["sql: |", indent(sql_de(v, m), "  ")]
    return "\n".join(out) + "\n"


def _wrap(texto, ancho=92):
    lineas, actual = [], ""
    for palabra in texto.split():
        if len(actual) + len(palabra) + 1 > ancho:
            lineas.append(actual)
            actual = palabra
        else:
            actual = f"{actual} {palabra}".strip()
    if actual:
        lineas.append(actual)
    return lineas


def main():
    from curaduria_vistas import VISTAS

    vistos, escritos = {}, 0
    for v in VISTAS:
        for m in v["medidas"]:
            if m["id"] in vistos:
                raise SystemExit(f"id duplicado: {m['id']} ({v['origen']} y {vistos[m['id']]})")
            vistos[m["id"]] = v["origen"]
            destino = DESTINO / v["tema"] / f"{m['id']}.yaml"
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(yaml_de(v, m), encoding="utf-8")
            escritos += 1
    print(f"{escritos} indicadores escritos en {DESTINO}")


if __name__ == "__main__":
    main()
