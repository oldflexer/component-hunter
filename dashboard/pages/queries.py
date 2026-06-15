import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from dnsight.services.component_service import ComponentService
from dnsight.config.attributes import ATTR_MODEL
from dnsight.core.models import Model, AttributeValue, Product, ProductType
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
        # Motherboard – оптимизированная загрузка
        type_obj = db.query(ProductType).filter_by(name="Motherboard").first()
        if not type_obj:
            st.warning("Тип Motherboard не найден.")
            return
        products = db.query(Product).filter_by(type_id=type_obj.id).all()
        product_ids = [p.id for p in products]

        # Загружаем все attribute_values для этих продуктов одним запросом
        attrs = db.query(AttributeValue).filter(AttributeValue.product_id.in_(product_ids)).all()
        attr_dict_by_product = {}
        for av in attrs:
            attr_dict_by_product.setdefault(av.product_id, {})[av.attribute.name] = av.raw_value

        data = []
        for prod in products:
            model_name = None
            if prod.model_id:
                model = db.query(Model).filter_by(id=prod.model_id).first()
                if model:
                    model_name = model.name
            if not model_name:
                model_name = attr_dict_by_product.get(prod.id, {}).get(ATTR_MODEL, "")
            score = get_last_score(db, prod.model_id) if prod.model_id else 0
            price = get_last_price(db, prod.id)
            if price is None:
                continue
            benefit = get_last_benefit(db, prod.id) or 0.0
            data.append({
                "product_name": prod.name,
                "model_name": model_name,
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
    st.dataframe(df[["product_name", "model_name", "score", "price", "benefit", "benefit %"]], width='stretch', height=600)


def render(db: Session):
    tab_cpu, tab_gpu, tab_mb = st.tabs(["CPU", "GPU", "Motherboard"])
    with tab_cpu:
        build_component_table(db, "CPU")
    with tab_gpu:
        build_component_table(db, "GPU")
    with tab_mb:
        build_component_table(db, "Motherboard")