from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from ..core.models import Product, PriceHistory, ModelScore, BenefitHistory
from sqlalchemy import desc
from ..core.logging import get_logger

logger = get_logger("benefit", "logs/benefit.log", mode='a')

def get_current_score(product: Product, db: Session) -> Optional[float]:
    if product.model_id is None:
        return None
    score_record = db.query(ModelScore).filter_by(model_id=product.model_id).order_by(desc(ModelScore.updated_at)).first()
    return score_record.score if score_record else None # pyright: ignore[reportReturnType]

def get_last_price(product_id: int, db: Session) -> Optional[float]:
    price_record = db.query(PriceHistory).filter_by(product_id=product_id).order_by(desc(PriceHistory.timestamp)).first()
    return price_record.price if price_record else None # pyright: ignore[reportReturnType]

def calculate_benefit(score: float, price: float) -> float:
    if price > 0 and score:
        return score / price
    return 0.0

def update_benefit_for_product(product: Product, db: Session) -> None:
    score = get_current_score(product, db)
    if score is None:
        return
    price = get_last_price(product.id, db)
    if price is None:
        return
    benefit = calculate_benefit(score, price)
    benefit_history = BenefitHistory(
        product_id=product.id,
        benefit=benefit,
        timestamp=datetime.utcnow()
    )
    db.add(benefit_history)
    db.commit()
    logger.info(f"Benefit для продукта {product.id}: {benefit}")