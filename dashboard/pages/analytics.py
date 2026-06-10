import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy.orm import Session
from typing import Optional
from dnsight.core.models import ProductType, Product, PriceHistory, ModelScore, BenefitHistory


def get_type_id(db: Session, component_type: str) -> Optional[int]:
    pt = db.query(ProductType).filter_by(name=component_type).first()
    return pt.id if pt else None


def get_daily_averages(db: Session, component_type: str):
    type_id = get_type_id(db, component_type)
    if type_id is None:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    products = db.query(Product).filter_by(type_id=type_id).all()
    product_ids = [p.id for p in products]
    if not product_ids:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Средняя цена
    prices = db.query(PriceHistory).filter(PriceHistory.product_id.in_(product_ids)).all()
    df_price = pd.DataFrame([(p.timestamp.date(), p.price) for p in prices], columns=["date", "price"])
    if not df_price.empty:
        avg_price = df_price.groupby("date")["price"].mean().reset_index()
        avg_price.columns = ["date", "avg_price"]
    else:
        avg_price = pd.DataFrame(columns=["date", "avg_price"])

    # Средний балл PassMark
    model_ids = [p.model_id for p in products if p.model_id is not None]
    scores = db.query(ModelScore).filter(ModelScore.model_id.in_(model_ids)).all()
    df_score = pd.DataFrame([(s.updated_at.date(), s.score) for s in scores], columns=["date", "score"])
    if not df_score.empty:
        avg_score = df_score.groupby("date")["score"].mean().reset_index()
        avg_score.columns = ["date", "avg_score"]
    else:
        avg_score = pd.DataFrame(columns=["date", "avg_score"])

    # Средний Benefit
    benefits = db.query(BenefitHistory).filter(BenefitHistory.product_id.in_(product_ids)).all()
    df_benefit = pd.DataFrame([(b.timestamp.date(), b.benefit) for b in benefits], columns=["date", "benefit"])
    if not df_benefit.empty:
        avg_benefit = df_benefit.groupby("date")["benefit"].mean().reset_index()
        avg_benefit.columns = ["date", "avg_benefit"]
    else:
        avg_benefit = pd.DataFrame(columns=["date", "avg_benefit"])

    return avg_price, avg_score, avg_benefit


def plot_trends(db: Session, component_type: str):
    avg_price, avg_score, avg_benefit = get_daily_averages(db, component_type)
    if avg_price.empty and avg_score.empty and avg_benefit.empty:
        st.info(f"Нет данных для {component_type}")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        if not avg_price.empty:
            fig = px.line(avg_price, x="date", y="avg_price",
                          title=f"Средняя цена {component_type}",
                          labels={"avg_price": "₽", "date": "Дата"})
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("Нет данных о ценах")
    with col2:
        if not avg_score.empty:
            fig = px.line(avg_score, x="date", y="avg_score",
                          title=f"Средний балл PassMark {component_type}",
                          labels={"avg_score": "баллы", "date": "Дата"})
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("Нет данных о скорах")
    with col3:
        if not avg_benefit.empty:
            fig = px.line(avg_benefit, x="date", y="avg_benefit",
                          title=f"Средний Benefit {component_type}",
                          labels={"avg_benefit": "Benefit", "date": "Дата"})
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("Нет данных о Benefit")


def render(db: Session):
    cpu_tab, gpu_tab = st.tabs(["CPU", "GPU"])
    with cpu_tab:
        plot_trends(db, "CPU")
    with gpu_tab:
        plot_trends(db, "GPU")