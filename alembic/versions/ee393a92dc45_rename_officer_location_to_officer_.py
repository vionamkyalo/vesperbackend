"""rename officer_location to officer_assignment

Revision ID: ee393a92dc45
Revises: fb1a2f51e196
"""

from typing import Sequence, Union

from alembic import op


revision: str = "ee393a92dc45"
down_revision: Union[str, Sequence[str], None] = "fb1a2f51e196"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("officer_location", "officer_assignment")


def downgrade() -> None:
    op.rename_table("officer_assignment", "officer_location")
