from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from ..core.models import Component, PriceHistory, ModelScore, BenefitHistory
from sqlalchemy import desc
from ..core.logging import get_logger

logger = get_logger("benefit", "logs/benefit.log", mode='a')

def get_current_score(component: Component, db: Session) -> Optional[float]:
    if component.model_id is None:
        return None
    score_record = db.query(ModelScore).filter_by(model_id=component.model_id).order_by(desc(ModelScore.updated_at)).first()
    return score_record.score if score_record else None

def get_last_price(component_id: int, db: Session) -> Optional[float]:
    price_record = db.query(PriceHistory).filter_by(component_id=component_id).order_by(desc(PriceHistory.timestamp)).first()
    return price_record.price if price_record else None

def calculate_benefit(score: float, price: float) -> float:
    if price and price > 0 and score:
        return score / (price * price)
    return 0.0

def update_benefit_for_component(component: Component, db: Session) -> None:
    score = get_current_score(component, db)
    if score is None:
        return
    price = get_last_price(component.id, db)
    if price is None:
        return
    benefit = calculate_benefit(score, price)
    # Добавляем новую запись в историю Benefit
    benefit_history = BenefitHistory(
        component_id=component.id,
        benefit=benefit,
        timestamp=datetime.utcnow()
    )
    db.add(benefit_history)
    db.commit()
    logger.info(f"Benefit для компонента {component.id}: {benefit}")