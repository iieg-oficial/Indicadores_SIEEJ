"""CLI de operación: listar, describir, ejecutar y validar.

Sirve para depurar sin levantar el servidor — que es justo lo que hace falta mientras
las superficies MCP y REST todavía no existen.

**El JSON va a stdout; todo log va a stderr.** Es lo que lo hace encadenable con jq.
"""

import argparse
import json
import logging
import sys

from indicadores_sieej import motor
from indicadores_sieej.catalogo import CATALOGO, cargar, listar, obtener
from indicadores_sieej.errores import CatalogoInvalido, ErrorDelBanco

# Nada de logging puede ensuciar stdout: ahí solo va el JSON.
logging.basicConfig(stream=sys.stderr)


def _params(pares: list[str]) -> dict:
    try:
        return dict(par.split("=", 1) for par in pares)
    except ValueError:
        raise SystemExit("Los parámetros van como -p nombre=valor") from None


def _validar() -> int:
    """Corre las siete validaciones sobre el catálogo. Es el gate de CI."""
    try:
        indicadores = cargar()
    except CatalogoInvalido as exc:
        print(f"catálogo inválido: {exc}", file=sys.stderr)
        return 1
    print(f"{len(indicadores)} indicadores válidos en {CATALOGO}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m indicadores_sieej.cli", description="Banco de indicadores")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_listar = sub.add_parser("listar", help="Lista los indicadores del catálogo")
    p_listar.add_argument("--tema")
    p_listar.add_argument("--nivel", choices=["nacional", "estatal", "municipal"])

    p_describir = sub.add_parser("describir", help="Metadata completa de un indicador, sin el sql")
    p_describir.add_argument("id")

    p_ejecutar = sub.add_parser("ejecutar", help="Ejecuta un indicador y devuelve los datos")
    p_ejecutar.add_argument("id")
    p_ejecutar.add_argument("-p", dest="params", action="append", default=[], metavar="nombre=valor")

    sub.add_parser("validar", help="Valida el catálogo; sale con código distinto de cero si falla")

    args = parser.parse_args(argv)

    if args.comando == "validar":
        return _validar()

    try:
        if args.comando == "listar":
            salida = listar(tema=args.tema, nivel=args.nivel)
        elif args.comando == "describir":
            salida = obtener(args.id).metadata()
        else:
            salida = motor.ejecutar(args.id, **_params(args.params))
    except ErrorDelBanco as exc:
        print(f"{exc}", file=sys.stderr)
        return 1

    print(json.dumps(salida, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
