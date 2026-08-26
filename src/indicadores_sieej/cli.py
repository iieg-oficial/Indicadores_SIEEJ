"""CLI de operación: listar, describir, ejecutar y validar.

Sirve para depurar sin levantar el servidor — que es justo lo que hace falta mientras
las superficies MCP y REST todavía no existen.

Los subcomandos y sus flags van en español porque nombran campos del catálogo y son
la superficie que usa el analista, no vocabulario interno.

**El JSON va a stdout; todo log va a stderr.** Es lo que lo hace encadenable con jq.
"""

import argparse
import json
import logging
import sys

from indicadores_sieej import engine
from indicadores_sieej.catalog import CATALOG_DIR, find, get, load
from indicadores_sieej.errors import BankError, InvalidCatalog

# Nada de logging puede ensuciar stdout: ahí solo va el JSON.
logging.basicConfig(stream=sys.stderr)


def _params(pairs: list[str]) -> dict:
    try:
        return dict(pair.split("=", 1) for pair in pairs)
    except ValueError:
        raise SystemExit("Los parámetros van como -p nombre=valor") from None


def _validate() -> int:
    """Corre las siete validaciones sobre el catálogo. Es el gate de CI."""
    try:
        indicators = load()
    except InvalidCatalog as exc:
        print(f"catálogo inválido: {exc}", file=sys.stderr)
        return 1
    print(f"{len(indicators)} indicadores válidos en {CATALOG_DIR}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m indicadores_sieej.cli", description="Banco de indicadores")
    sub = parser.add_subparsers(dest="command", required=True)

    p_find = sub.add_parser("listar", help="Lista los indicadores del catálogo")
    p_find.add_argument("--tema")
    p_find.add_argument("--nivel", choices=["nacional", "estatal", "municipal"])

    p_get = sub.add_parser("describir", help="Metadata completa de un indicador, sin el sql")
    p_get.add_argument("id")

    p_execute = sub.add_parser("ejecutar", help="Ejecuta un indicador y devuelve los datos")
    p_execute.add_argument("id")
    p_execute.add_argument("-p", dest="params", action="append", default=[], metavar="nombre=valor")

    sub.add_parser("validar", help="Valida el catálogo; sale con código distinto de cero si falla")

    args = parser.parse_args(argv)

    if args.command == "validar":
        return _validate()

    try:
        if args.command == "listar":
            output = find(tema=args.tema, nivel=args.nivel)
        elif args.command == "describir":
            output = get(args.id).metadata()
        else:
            output = engine.execute(args.id, _params(args.params))
    except BankError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1

    print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
