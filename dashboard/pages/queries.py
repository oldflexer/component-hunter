import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from dnsight.core.models import ProductType, Product, Model
from dashboard.utils import get_last_score, get_last_price, get_last_benefit


def build_component_table(db: Session, component_type: str):
    type_obj = db.query(ProductType).filter_by(name=component_type).first()
    if not type_obj:
        st.warning(f"Тип {component_type} не найден.")
        return

    products = db.query(Product).filter_by(type_id=type_obj.id).all()
    data = []
    for prod in products:
        if prod.model_id is None:
            continue
        model = db.query(Model).filter_by(id=prod.model_id).first()
        if not model:
            continue
        score = get_last_score(db, model.id)
        if score is None:
            continue
        price = get_last_price(db, prod.id)
        if price is None:
            continue
        benefit = get_last_benefit(db, prod.id) or 0.0
        data.append({
            "product_name": prod.name,
            "model_name": model.name,
            "score": score,
            "price": price,
            "benefit": benefit,
        })
    if not data:
        st.info(f"Нет данных для {component_type}.")
        return

    df = pd.DataFrame(data)
    max_benefit = df['benefit'].max()
    df['benefit %'] = (df['benefit'] / max_benefit * 100).round(1) if max_benefit > 0 else 0
    df = df.sort_values(by="benefit", ascending=False)
    st.dataframe(df[["product_name", "model_name", "score", "price", "benefit", "benefit %"]], width='stretch')


def render(db: Session):
    tab_cpu, tab_gpu = st.tabs(["CPU", "GPU"])
    with tab_cpu:
        build_component_table(db, "CPU")
    with tab_gpu:
        build_component_table(db, "GPU")