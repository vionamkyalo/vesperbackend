from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c0625ad69c0f"
down_revision: Union[str, None] = "58ddb8f55a51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "catch_check",
        sa.Column("type_of_fish", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "catch_check",
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "catch_check",
        sa.Column("catch_per_rig_night", sa.Numeric(10, 2), nullable=True),
    )

    op.execute(
        "UPDATE catch_check SET catch_per_rig_night = "
        "COALESCE(ROUND(catch_weight_kg / NULLIF(rig_nights, 0), 2), 0)"
    )

    with op.batch_alter_table("catch_check") as batch_op:
        batch_op.alter_column(
            "catch_per_rig_night",
            existing_type=sa.Numeric(10, 2),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("catch_check") as batch_op:
        batch_op.drop_column("catch_per_rig_night")
        batch_op.drop_column("notes")
        batch_op.drop_column("type_of_fish")
