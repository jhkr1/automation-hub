"""create trend snapshots table."""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0002_create_trend_snapshots"
down_revision: Union[str, None] = "0001_initial_empty"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the raw trend snapshot table."""
    op.create_table(
        "trend_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.Column("collection_date", sa.Date(), nullable=False),
        sa.Column("rank_position", sa.SmallInteger(), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "rank_position BETWEEN 1 AND 10", name="ck_trend_snapshots_rank_range"
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(TRIM(keyword)) > 0", name="ck_trend_snapshots_keyword_nonempty"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trend_snapshots"),
        sa.UniqueConstraint(
            "collected_at", "rank_position", name="uq_trend_snapshots_collected_rank"
        ),
    )
    op.create_index(
        "ix_trend_snapshots_collection_date_keyword",
        "trend_snapshots",
        ["collection_date", "keyword"],
    )


def downgrade() -> None:
    """Drop the trend snapshot table."""
    op.drop_index("ix_trend_snapshots_collection_date_keyword", table_name="trend_snapshots")
    op.drop_table("trend_snapshots")
