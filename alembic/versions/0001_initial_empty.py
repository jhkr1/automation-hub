"""Initial empty migration."""

from typing import Sequence, Union

revision: str = "0001_initial_empty"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the initial empty schema migration."""


def downgrade() -> None:
    """Revert the initial empty schema migration."""
