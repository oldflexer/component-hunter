# scripts/list_mb_attributes.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dnsight.core.database import get_db
from dnsight.core.models import ProductType, Product, Attribute, AttributeValue

db = get_db()
mb_type = db.query(ProductType).filter_by(name="Motherboard").first()
if mb_type:
    prod = db.query(Product).filter_by(type_id=mb_type.id).first()
    if prod:
        attrs = db.query(AttributeValue).filter_by(product_id=prod.id).all()
        print("Существующие атрибуты для материнской платы:")
        for av in attrs:
            print(f"  {av.attribute.name}: {av.raw_value}")