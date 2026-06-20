"""add missing indexes

Revision ID: 4062289d7bc0
Revises: 6480f1f24d20
Create Date: 2026-06-20 19:13:50.166044

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4062289d7bc0'
down_revision: Union[str, Sequence[str], None] = '6480f1f24d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('idx_products_type_id', 'products', ['type_id'])
    op.create_index('idx_products_model_id', 'products', ['model_id'])
    op.create_index('idx_models_type_id', 'models', ['type_id'])
    op.create_index('idx_model_scores_model_id', 'model_scores', ['model_id'])
    op.create_index('idx_attribute_values_product_id', 'attribute_values', ['product_id'])
    op.create_index('idx_attribute_values_attribute_id', 'attribute_values', ['attribute_id'])
    op.create_index('idx_price_history_product_id', 'price_history', ['product_id'])
    op.create_index('idx_benefit_history_product_id', 'benefit_history', ['product_id'])
    pass


def downgrade() -> None:
    op.drop_index('idx_products_type_id', 'products')
    op.drop_index('idx_products_model_id', 'products')
    op.drop_index('idx_models_type_id', 'models')
    op.drop_index('idx_model_scores_model_id', 'model_scores')
    op.drop_index('idx_attribute_values_product_id', 'attribute_values')
    op.drop_index('idx_attribute_values_attribute_id', 'attribute_values')
    op.drop_index('idx_price_history_product_id', 'price_history')
    op.drop_index('idx_benefit_history_product_id', 'benefit_history')
    pass
