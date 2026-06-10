import streamlit as st
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from dnsight.core.models import ProductType, Product, Model, PriceHistory, ModelScore, BenefitHistory
from dashboard.utils import get_last_benefit, get_last_score


def get_current_and_prev_avg(db: Session, component_type: str, days_ago: int = 7):
    type_obj = db.query(ProductType).filter_by(name=component_type).first()
    if not type_obj:
        return None
    products = db.query(Product).filter_by(type_id=type_obj.id).all()
    product_ids = [p.id for p in products]

    # средняя цена сегодня
    prices_today = []
    for pid in product_ids:
        ph = db.query(PriceHistory).filter_by(product_id=pid).order_by(PriceHistory.timestamp.desc()).first()
        if ph and ph.price:
            prices_today.append(ph.price)
    avg_price_now = sum(prices_today) / len(prices_today) if prices_today else 0.0

    # средняя цена days_ago дней назад
    cutoff = datetime.now() - timedelta(days=days_ago)
    prices_prev = []
    for pid in product_ids:
        ph = db.query(PriceHistory).filter(
            PriceHistory.product_id == pid,
            PriceHistory.timestamp <= cutoff
        ).order_by(PriceHistory.timestamp.desc()).first()
        if ph and ph.price:
            prices_prev.append(ph.price)
    avg_price_prev = sum(prices_prev) / len(prices_prev) if prices_prev else avg_price_now

    # средний скор сегодня
    scores_now = []
    for prod in products:
        if prod.model_id:
            sc = get_last_score(db, prod.model_id)
            if sc:
                scores_now.append(sc)
    avg_score_now = sum(scores_now) / len(scores_now) if scores_now else 0.0

    # средний скор days_ago назад
    scores_prev = []
    for prod in products:
        if prod.model_id:
            prev_score = db.query(ModelScore).filter(
                ModelScore.model_id == prod.model_id,
                ModelScore.updated_at <= cutoff
            ).order_by(ModelScore.updated_at.desc()).first()
            if prev_score and prev_score.score:
                scores_prev.append(prev_score.score)
    avg_score_prev = sum(scores_prev) / len(scores_prev) if scores_prev else avg_score_now

    # средний benefit сегодня
    benefit_now = []
    for pid in product_ids:
        bh = db.query(BenefitHistory).filter_by(product_id=pid).order_by(BenefitHistory.timestamp.desc()).first()
        if bh and bh.benefit:
            benefit_now.append(bh.benefit)
    avg_benefit_now = sum(benefit_now) / len(benefit_now) if benefit_now else 0.0

    # средний benefit days_ago назад
    benefit_prev = []
    for pid in product_ids:
        bh = db.query(BenefitHistory).filter(
            BenefitHistory.product_id == pid,
            BenefitHistory.timestamp <= cutoff
        ).order_by(BenefitHistory.timestamp.desc()).first()
        if bh and bh.benefit:
            benefit_prev.append(bh.benefit)
    avg_benefit_prev = sum(benefit_prev) / len(benefit_prev) if benefit_prev else avg_benefit_now

    return {
        "price_now": avg_price_now,
        "price_prev": avg_price_prev,
        "score_now": avg_score_now,
        "score_prev": avg_score_prev,
        "benefit_now": avg_benefit_now,
        "benefit_prev": avg_benefit_prev,
    }


def get_top_benefit(db: Session, component_type: str, top_n: int = 3):
    type_obj = db.query(ProductType).filter_by(name=component_type).first()
    if not type_obj:
        return []
    products = db.query(Product).filter_by(type_id=type_obj.id).all()
    items = []
    for prod in products:
        if prod.model_id is None:
            continue
        benefit = get_last_benefit(db, prod.id)
        if benefit is None or benefit <= 0:
            continue
        items.append({
            "name": prod.name,
            "model": prod.model.name if prod.model else "—",
            "benefit": benefit
        })
    items.sort(key=lambda x: x["benefit"], reverse=True)
    return items[:top_n]


def render(db: Session):
    st.header("📈 Общая сводка")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔲 CPU")
        stats = get_current_and_prev_avg(db, "CPU")
        if stats:
            st.metric("Средняя цена (₽)", f"{stats['price_now']:.0f}",
                      delta=f"{stats['price_now'] - stats['price_prev']:.0f}",
                      delta_color="inverse")
            st.metric("Средний балл PassMark", f"{stats['score_now']:.0f}",
                      delta=f"{stats['score_now'] - stats['score_prev']:.0f}",)
            st.metric("Средний Benefit", f"{stats['benefit_now']:.4f}",
                      delta=f"{stats['benefit_now'] - stats['benefit_prev']:.4f}")
        else:
            st.info("Нет данных по CPU")

        st.subheader("🏆 Топ-3 CPU по Benefit")
        top = get_top_benefit(db, "CPU")
        if top:
            for i, item in enumerate(top, 1):
                st.write(f"{i}. **{item['name']}** – Benefit {item['benefit']:.4f}")
        else:
            st.info("Нет данных")

    with col2:
        st.subheader("🎮 GPU")
        stats = get_current_and_prev_avg(db, "GPU")
        if stats:
            st.metric("Средняя цена (₽)", f"{stats['price_now']:.0f}",
                      delta=f"{stats['price_now'] - stats['price_prev']:.0f}",
                      delta_color="inverse")
            st.metric("Средний балл PassMark", f"{stats['score_now']:.0f}",
                      delta=f"{stats['score_now'] - stats['score_prev']:.0f}")
            st.metric("Средний Benefit", f"{stats['benefit_now']:.4f}",
                      delta=f"{stats['benefit_now'] - stats['benefit_prev']:.4f}")
        else:
            st.info("Нет данных по GPU")

        st.subheader("🏆 Топ-3 GPU по Benefit")
        top = get_top_benefit(db, "GPU")
        if top:
            for i, item in enumerate(top, 1):
                st.write(f"{i}. **{item['name']}** – Benefit {item['benefit']:.4f}")
        else:
            st.info("Нет данных")