"""Google Finance stock quote snapshots table."""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0003_stock_quote_snapshots"
down_revision: Union[str, None] = "0002_create_trend_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the append-only Google Finance snapshot table."""
    op.create_table(
        "stock_quote_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("current_price", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("previous_close", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("open_price", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("change_percent", sa.Numeric(precision=12, scale=8), nullable=False),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "CHAR_LENGTH(TRIM(symbol)) > 0",
            name="ck_stock_quote_snapshots_symbol_nonempty",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(TRIM(name)) > 0",
            name="ck_stock_quote_snapshots_name_nonempty",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(currency) = 3",
            name="ck_stock_quote_snapshots_currency_length",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_stock_quote_snapshots"),
    )
    op.create_index(
        "ix_stock_quote_snapshots_symbol_collected_at",
        "stock_quote_snapshots",
        ["symbol", "collected_at"],
    )


def downgrade() -> None:
    """Drop only the Google Finance snapshot table."""
    op.drop_index(
        "ix_stock_quote_snapshots_symbol_collected_at",
        table_name="stock_quote_snapshots",
    )
    op.drop_table("stock_quote_snapshots")
