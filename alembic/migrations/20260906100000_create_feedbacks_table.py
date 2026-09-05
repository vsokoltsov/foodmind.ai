"""Create the user feedback table for assistant messages."""

from alembic import op
import sqlalchemy as sa

revision = "20260906100000"
down_revision = "20260903130000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create one updatable feedback row per user and assistant message."""
    op.create_table(
        "feedbacks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("is_useful", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id"),
    )
    op.create_index("ix_feedbacks_message_id", "feedbacks", ["message_id"])
    op.create_index("ix_feedbacks_user_id", "feedbacks", ["user_id"])


def downgrade() -> None:
    """Drop the feedback table and its indexes."""
    op.drop_index("ix_feedbacks_user_id", table_name="feedbacks")
    op.drop_index("ix_feedbacks_message_id", table_name="feedbacks")
    op.drop_table("feedbacks")
