import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import text
from concurrent.futures import ThreadPoolExecutor
from dnsight.core.database import SessionLocal
from dnsight.core.models import PriceHistory, ProductType, Product, ModelScore, Model
from dnsight.config.settings import CACHE_TTL


def render_problem_table(db: Session, title: str, df: pd.DataFrame, product_ids: list, key_suffix: str):
    if df.empty:
        st.success(f"✅ {title} – проблем нет!")
        return

    st.subheader(title)
    df_with_check = df.copy()
    df_with_check.insert(0, "🗑️", False)
    column_config = {"🗑️": st.column_config.CheckboxColumn(label="", width=30, default=False)}
    edited_df = st.data_editor(df_with_check, column_config=column_config, width='stretch',
                               hide_index=True, key=f"diagnostic_{key_suffix}")

    if st.button(f"🗑️ Выбрать товары для удаления", key=f"del_select_{key_suffix}"):
        selected_mask = edited_df["🗑️"] == True
        if selected_mask.any():
            ids_to_delete = edited_df.loc[selected_mask, "ID"].tolist()
            st.session_state[f"to_delete_{key_suffix}"] = ids_to_delete
            st.session_state[f"show_confirm_{key_suffix}"] = True
        else:
            st.info("Нет выбранных товаров.")

    if st.session_state.get(f"show_confirm_{key_suffix}", False):
        ids_to_delete = st.session_state.get(f"to_delete_{key_suffix}", [])
        if ids_to_delete:
            st.warning(f"Вы собираетесь удалить {len(ids_to_delete)} товаров. Это действие необратимо!")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Да, удалить", key=f"confirm_yes_{key_suffix}"):
                    try:
                        products_to_delete = db.query(Product).filter(Product.id.in_(ids_to_delete)).all()
                        for prod in products_to_delete:
                            db.delete(prod)
                        db.commit()
                        st.cache_data.clear()
                        st.success(f"Удалено {len(products_to_delete)} товаров.")
                        st.session_state[f"show_confirm_{key_suffix}"] = False
                        st.session_state[f"to_delete_{key_suffix}"] = []
                        st.rerun()
                    except Exception as e:
                        db.rollback()
                        st.error(f"Ошибка удаления: {type(e).__name__}: {e}")
            with col2:
                if st.button("❌ Отмена", key=f"confirm_no_{key_suffix}"):
                    st.session_state[f"show_confirm_{key_suffix}"] = False
                    st.session_state[f"to_delete_{key_suffix}"] = []
                    st.rerun()


@st.cache_data(ttl=CACHE_TTL)
def get_diagnostic_data(type_name: str, type_id: int):
    db = SessionLocal()
    try:
        # Без характеристик
        products_no_attrs = db.query(Product).filter(
            Product.type_id == type_id,
            ~Product.attribute_values.any()
        ).all()
        no_attrs = [(p.id, p.name, p.url) for p in products_no_attrs]

        # Без баллов (если есть модели)
        has_models = db.query(Model).filter_by(type_id=type_id).first() is not None
        no_scores = []
        if has_models:
            model_ids_with_scores = [row[0] for row in db.query(ModelScore.model_id).distinct().all()]
            products_no_scores = db.query(Product).filter(
                Product.type_id == type_id,
                Product.model_id.isnot(None),
                Product.model_id.notin_(model_ids_with_scores)
            ).all()
            no_scores = [(p.id, p.name, p.model.name if p.model else "Нет модели", p.url) for p in products_no_scores]

        # Без цены
        product_ids_with_price = [row[0] for row in db.query(PriceHistory.product_id).distinct().all()]
        products_no_price = db.query(Product).filter(
            Product.type_id == type_id,
            Product.id.notin_(product_ids_with_price)
        ).all()
        no_price = [(p.id, p.name, p.url) for p in products_no_price]

        return {
            "no_attrs": no_attrs,
            "no_scores": no_scores,
            "no_price": no_price,
        }
    finally:
        db.close()


def render(db: Session):
    # Получаем типы через переданную сессию
    product_types = db.query(ProductType).order_by(ProductType.name).all()
    types_with_products = [
        pt for pt in product_types
        if db.query(Product).filter_by(type_id=pt.id).first() is not None
    ]

    if not types_with_products:
        st.info("Нет данных о типах продуктов в БД.")
        return

    # Загружаем данные для всех типов параллельно
    with ThreadPoolExecutor() as executor:
        futures = {pt.name: executor.submit(get_diagnostic_data, pt.name, pt.id) for pt in types_with_products}
        data_by_type = {name: future.result() for name, future in futures.items()}

    tabs = st.tabs([pt.name for pt in types_with_products])
    for tab, pt in zip(tabs, types_with_products):
        with tab:
            data = data_by_type[pt.name]
            # Без характеристик
            if data["no_attrs"]:
                df = pd.DataFrame(data["no_attrs"], columns=["ID", "Name", "URL"])
                render_problem_table(db, f"{pt.name} – без характеристик", df, [p[0] for p in data["no_attrs"]], f"{pt.name.lower()}_no_attrs")
            else:
                st.success(f"✅ {pt.name} – без характеристик: проблем нет!")

            # Без баллов
            if data["no_scores"]:
                df = pd.DataFrame(data["no_scores"], columns=["ID", "Name", "Model Name", "URL"])
                render_problem_table(db, f"{pt.name} – без баллов", df, [p[0] for p in data["no_scores"]], f"{pt.name.lower()}_no_scores")
            else:
                st.success(f"✅ {pt.name} – без баллов: проблем нет!")

            # Без цены
            if data["no_price"]:
                df = pd.DataFrame(data["no_price"], columns=["ID", "Name", "URL"])
                render_problem_table(db, f"{pt.name} – без цены", df, [p[0] for p in data["no_price"]], f"{pt.name.lower()}_no_price")
            else:
                st.success(f"✅ {pt.name} – без цены: проблем нет!")