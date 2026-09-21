"""Add messages table for conversational thread history

Revision ID: 0002_add_messages_table
Revises: 0001_initial_legal_schema
Create Date: 2026-09-21 19:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_add_messages_table"
down_revision: Union[str, None] = "0001_initial_legal_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "messages" not in tables:
        op.create_table(
            "messages",
            sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("thread_id", sa.Uuid(), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column(
                "sources",
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                server_default=sa.text("'[]'::jsonb" if conn.dialect.name == "postgresql" else "'[]'"),
                nullable=False,
            ),
            sa.Column("tokens_used", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_messages_id", "messages", ["id"], unique=False)
        op.create_index("idx_messages_thread_id", "messages", ["thread_id", "created_at"], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "messages" in tables:
        op.drop_index("idx_messages_thread_id", table_name="messages")
        op.drop_index("ix_messages_id", table_name="messages")
        op.drop_table("messages")
