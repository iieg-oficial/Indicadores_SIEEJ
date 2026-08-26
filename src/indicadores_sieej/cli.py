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

from alembic.util import CommandError
from sqlalchemy.exc import SQLAlchemyError

from indicadores_sieej import engine, registry
from indicadores_sieej.catalog import CATALOG_DIR, find, get, load
from indicadores_sieej.errors import BankError, InvalidCatalog, RegistryUnavailable

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


def _migrate() -> int:
    """Aplica el esquema del registro de tokens. **No corre al arrancar el servidor.**

    Es deliberado, y es la convención de ETL-SIEEJ: el esquema se aplica a mano en el
    despliegue, no como efecto secundario de levantar el servicio. Así el rol del
    servidor no necesita permisos de DDL en operación normal.
    """
    try:
        registry.migrate()
    except RegistryUnavailable as exc:
        print(f"{exc}", file=sys.stderr)
        return 1
    except (SQLAlchemyError, CommandError) as exc:
        # Sin la excepción completa: el texto de un error de conexión trae el DSN.
        print(f"no se pudo migrar el registro: {type(exc).__name__}", file=sys.stderr)
        return 1
    print("registro de tokens al día", file=sys.stderr)
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

    sub.add_parser("migrar", help="Aplica el esquema del registro de tokens")

    args = parser.parse_args(argv)

    if args.command == "validar":
        return _validate()

    if args.command == "migrar":
        return _migrate()

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
