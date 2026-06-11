import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from dnsight.core.models import ProductType, Product, PriceHistory, ModelScore, BenefitHistory


def plot_product_history(db: Session, component_type: str):
    type_obj = db.query(ProductType).filter_by(name=component_type).first()
    if not type_obj:
        st.warning(f"Нет данных для {component_type}")
        return
    products = db.query(Product).filter_by(type_id=type_obj.id).all()
    if not products:
        st.info(f"Нет продуктов типа {component_type}")
        return

    product_options = {p.name: p.id for p in products}
    selected_name = st.selectbox(f"Выберите {component_type}", list(product_options.keys()), key=f"select_{component_type}")
    selected_id = product_options[selected_name]
    selected_product = next(p for p in products if p.id == selected_id)

    thirty_days_ago = datetime.now() - timedelta(days=30)

    prices = db.query(PriceHistory).filter(
        PriceHistory.product_id == selected_id,
        PriceHistory.timestamp >= thirty_days_ago
    ).order_by(PriceHistory.timestamp).all()
    df_price = pd.DataFrame([(p.timestamp, p.price) for p in prices], columns=["date", "price"])

    scores = []
    if selected_product.model_id:
        scores = db.query(ModelScore).filter(
            ModelScore.model_id == selected_product.model_id,
            ModelScore.updated_at >= thirty_days_ago
        ).order_by(ModelScore.updated_at).all()
    df_score = pd.DataFrame([(s.updated_at, s.score) for s in scores], columns=["date", "score"])

    benefits = db.query(BenefitHistory).filter(
        BenefitHistory.product_id == selected_id,
        BenefitHistory.timestamp >= thirty_days_ago
    ).order_by(BenefitHistory.timestamp).all()
    df_benefit = pd.DataFrame([(b.timestamp, b.benefit) for b in benefits], columns=["date", "benefit"])

    col1, col2, col3 = st.columns(3)
    with col1:
        if not df_price.empty:
            fig = px.line(df_price, x="date", y="price", title="Цена", labels={"price": "₽"})
            st.plotly_chart(fig, width='stretch', height=600)
        else:
            st.info("Нет данных о ценах за последние 30 дней")
    with col2:
        if not df_score.empty:
            fig = px.line(df_score, x="date", y="score", title="PassMark Score", labels={"score": "баллы"})
            st.plotly_chart(fig, width='stretch', height=600)
        else:
            st.info("Нет данных о скорах за последние 30 дней")
    with col3:
        if not df_benefit.empty:
            fig = px.line(df_benefit, x="date", y="benefit", title="Benefit", labels={"benefit": "Benefit"})
            st.plotly_chart(fig, width='stretch', height=600)
        else:
            st.info("Нет данных о Benefit за последние 30 дней")


def render(db: Session):
    cpu_tab, gpu_tab = st.tabs(["CPU", "GPU"])
    with cpu_tab:
        plot_product_history(db, "CPU")
    with gpu_tab:
        plot_product_history(db, "GPU")