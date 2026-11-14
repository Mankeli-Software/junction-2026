"""Track real SMS through Twilio on sms_messages (#46)

`twilio_sid` finds the row again from Twilio's status callback, `error_code` keeps
Twilio's code for a refused or undelivered message, and the `twilio` path gets two
statuses of its own: `pending` (committed, waiting to be sent) and `sending` (the request
to Twilio is on its way).

0005 named the status check `ck_sms_messages_ck_sms_messages_status` (the naming
convention was applied twice). It comes back under the name the model gives it.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = "status IN ('held', 'delivered', 'queued', 'sent', 'failed')"
NEW_STATUSES = "status IN ('held', 'pending', 'sending', 'delivered', 'queued', 'sent', 'failed')"
OLD_NAME = "ck_sms_messages_ck_sms_messages_status"
NEW_NAME = "ck_sms_messages_status"


def upgrade() -> None:
    op.add_column("sms_messages", sa.Column("twilio_sid", sa.Text(), nullable=True))
    op.add_column("sms_messages", sa.Column("error_code", sa.Text(), nullable=True))
    op.create_unique_constraint(op.f("uq_sms_messages_twilio_sid"), "sms_messages", ["twilio_sid"])
    op.execute(f"ALTER TABLE sms_messages DROP CONSTRAINT IF EXISTS {OLD_NAME}")
    op.execute(f"ALTER TABLE sms_messages DROP CONSTRAINT IF EXISTS {NEW_NAME}")
    op.create_check_constraint(op.f(NEW_NAME), "sms_messages", NEW_STATUSES)


def downgrade() -> None:
    op.execute("UPDATE sms_messages SET status = 'failed' WHERE status IN ('pending', 'sending')")
    op.drop_constraint(op.f(NEW_NAME), "sms_messages", type_="check")
    op.create_check_constraint(op.f(OLD_NAME), "sms_messages", OLD_STATUSES)
    op.drop_constraint(op.f("uq_sms_messages_twilio_sid"), "sms_messages", type_="unique")
    op.drop_column("sms_messages", "error_code")
    op.drop_column("sms_messages", "twilio_sid")
