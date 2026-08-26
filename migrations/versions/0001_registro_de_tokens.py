"""registro de tokens

Emisión de autoservicio: cualquiera pide un token con su correo y lo obtiene. Un token
activo por correo, y caducidad por desuso en vez de por antigüedad. Decidido en #29.

Revision ID: 0001_tokens
Revises:
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_tokens"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            # gen_random_uuid() es del núcleo desde PostgreSQL 13: no hace falta
            # pgcrypto, que exigiría superusuario para instalarse.
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            comment="Identidad del consumidor. Es lo que viaja a la auditoría, no el correo, que es dato personal.",
        ),
        sa.Column(
            "correo",
            sa.Text(),
            nullable=False,
            comment=(
                "Correo del solicitante, normalizado a minúsculas y sin espacios. "
                "Hoy solo es clave de unicidad: no está verificado."
            ),
        ),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
            comment="sha256 hexadecimal del token. El token en claro no se almacena en ninguna parte.",
        ),
        sa.Column(
            "prefijo",
            sa.Text(),
            nullable=False,
            comment=(
                "Primeros caracteres del token, sin valor secreto. Permite identificarlo en soporte sin conocerlo."
            ),
        ),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("ARRAY['indicadores:read']"),
            nullable=False,
            comment="Permisos del token. Los asigna el servidor; nunca se aceptan desde la petición.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Cuándo se emitió.",
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment=(
                "Última verificación exitosa. Se refresca de forma acotada, no en cada petición, "
                "y es contra esto que se mide la caducidad por desuso."
            ),
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Cuándo se revocó, o NULL si sigue activo. Reemitir para el mismo correo revoca el anterior.",
        ),
        # Sin normalizar, `A@b.mx` y `a@b.mx` son filas distintas y el índice parcial de
        # abajo deja de significar "un token por cuenta".
        sa.CheckConstraint("correo = lower(btrim(correo))", name="ck_tokens_correo_normalizado"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        comment="Tokens de acceso al banco de indicadores, emitidos por autoservicio en POST /v1/tokens.",
    )
    # Esto es lo que **realmente** impone un token activo por correo. Ordenar el UPDATE
    # antes del INSERT no basta: bajo READ COMMITTED la segunda transacción se desbloquea,
    # ve la fila ya revocada, actualiza cero filas e inserta igual.
    op.create_index(
        "uq_tokens_correo_activo",
        "tokens",
        ["correo"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_tokens_correo_activo", table_name="tokens")
    op.drop_table("tokens")
