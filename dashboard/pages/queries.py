import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor
from dnsight.core.database import SessionLocal
from dnsight.core.models import ProductType, Product, Model, AttributeValue
from dashboard.utils import get_last_price, get_last_benefit, get_last_score
from dnsight.config.attributes import ATTR_MODEL
from dnsight.config.settings import CACHE_TTL


@st.cache_data(ttl=CACHE_TTL)
def get_component_data(component_type: str):
    db = SessionLocal()
    try:
        type_obj = db.query(ProductType).filter_by(name=component_type).first()
        if not type_obj:
            return []
        products = db.query(Product).filter_by(type_id=type_obj.id).all()
        product_ids = [p.id for p in products]

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
            if not model_name:
                model_name = prod.name

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
        return data
    finally:
        db.close()


def render_table(component_data: list, component_type: str):
    if not component_data:
        st.info(f"Нет данных для {component_type}.")
        return
    df = pd.DataFrame(component_data)
    max_benefit = df['benefit'].max()
    df['benefit %'] = (df['benefit'] / max_benefit * 100).round(1) if max_benefit > 0 else 0
    df = df.sort_values(by="benefit", ascending=False)
    st.dataframe(df[["product_name", "model_name", "score", "price", "benefit", "benefit %"]], width='stretch', height=600)


def render(db: Session):
    product_types = db.query(ProductType).order_by(ProductType.name).all()
    types_with_products = [
        pt for pt in product_types
        if db.query(Product).filter_by(type_id=pt.id).first() is not None
    ]

    if not types_with_products:
        st.info("Нет данных о типах продуктов в БД.")
        return

    with ThreadPoolExecutor() as executor:
        futures = {pt.name: executor.submit(get_component_data, pt.name) for pt in types_with_products}
        data_by_type = {name: future.result() for name, future in futures.items()}

    tabs = st.tabs([pt.name for pt in types_with_products])
    for tab, pt in zip(tabs, types_with_products):
        with tab:
            render_table(data_by_type[pt.name], pt.name)