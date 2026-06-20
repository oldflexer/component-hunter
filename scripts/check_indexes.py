from dnsight.core.database import engine
from sqlalchemy import inspect

inspector = inspect(engine)
for table in ['products', 'models', 'model_scores', 'attribute_values', 'price_history', 'benefit_history']:
    indexes = inspector.get_indexes(table)
    print(f"\n{table}:")
    for idx in indexes:
        print(f"  {idx['name']} on {idx['column_names']}")