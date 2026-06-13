import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from dnsight.services.component_service import ComponentService
from dashboard.utils import get_last_price, get_last_benefit, get_last_score


def build_component_table(db: Session, component_type: str):
    service = ComponentService(db)
    if component_type == "CPU":
        components = service.get_cpu_components()
        data = []
        for comp in components:
            price = get_last_price(db, comp._product.id) if comp._product else 0
            benefit = comp.get_benefit()
            data.append({
                "product_name": comp.name,
                "model_name": comp.name,
                "score": comp.get_score(),
                "price": price,
                "benefit": benefit,
            })
    elif component_type == "GPU":
        components = service.get_gpu_components()
        data = []
        for comp in components:
            price = get_last_price(db, comp._product.id) if comp._product else 0
            benefit = comp.get_benefit()
            data.append({
                "product_name": comp.name,
                "model_name": comp.name,
                "score": comp.get_score(),
                "price": price,
                "benefit": benefit,
            })
    else:
        # Motherboard
        components = service.get_mb_components()
        data = []
        for comp in components:
            price = get_last_price(db, comp.product_id) if comp.product_id else 0
            benefit = comp.get_benefit()
            data.append({
                "product_name": comp.name,
                "model_name": comp.name,
                "score": comp.get_score(),
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
    st.dataframe(df[["product_name", "model_name", "score", "price", "benefit", "benefit %"]], width='stretch', height=600)


def render(db: Session):
    tab_cpu, tab_gpu, tab_mb = st.tabs(["CPU", "GPU", "Motherboard"])
    with tab_cpu:
        build_component_table(db, "CPU")
    with tab_gpu:
        build_component_table(db, "GPU")
    with tab_mb:
        build_component_table(db, "Motherboard")