"""add spread to zone_baseline

Revision ID: f31d9ef5d905
Revises: 58ddb8f55a51
Create Date: 2026-10-24 10:08:30.858817

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f31d9ef5d905"
down_revision: Union[str, Sequence[str], None] = "58ddb8f55a51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "zone_baseline",
        sa.Column(
            "spread",
            sa.Numeric(12, 4),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("zone_baseline") as batch_op:
        batch_op.drop_column("spread")
