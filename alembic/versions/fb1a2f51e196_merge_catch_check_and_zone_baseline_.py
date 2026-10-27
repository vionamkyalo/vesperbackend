"""merge catch check and zone baseline migrations

Revision ID: fb1a2f51e196
Revises: c0625ad69c0f, f31d9ef5d905
Create Date: 2026-10-24 12:54:30.313689

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "fb1a2f51e196"
down_revision: Union[str, Sequence[str], None] = ("c0625ad69c0f", "f31d9ef5d905")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
