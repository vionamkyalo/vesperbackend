"""rename officer_location to officer_assignment

Revision ID: ee393a92dc45
Revises: fb1a2f51e196
Create Date: 2026-10-29 17:03:11.016286

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "ee393a92dc45"
down_revision: Union[str, Sequence[str], None] = "fb1a2f51e196"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
