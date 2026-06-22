"""Add payment_provider and cryptopay_invoice_id to payments table

Revision ID: c4a7e9f2b31d
Revises: f8ff1805545b
Create Date: 2025-01-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4a7e9f2b31d'
down_revision: Union[str, None] = 'f8ff1805545b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payments', sa.Column('payment_provider', sa.String(), nullable=False, server_default='yookassa'), schema='public')
    op.add_column('payments', sa.Column('cryptopay_invoice_id', sa.String(), nullable=True), schema='public')
    op.create_unique_constraint('uq_payments_cryptopay_invoice_id', 'payments', ['cryptopay_invoice_id'], schema='public')
    op.alter_column('payments', 'yookassa_payment_id', nullable=True, schema='public')


def downgrade() -> None:
    op.alter_column('payments', 'yookassa_payment_id', nullable=False, schema='public')
    op.drop_constraint('uq_payments_cryptopay_invoice_id', 'payments', schema='public')
    op.drop_column('payments', 'cryptopay_invoice_id', schema='public')
    op.drop_column('payments', 'payment_provider', schema='public')
