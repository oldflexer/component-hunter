import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import text
from dnsight.core.database import SessionLocal
from dnsight.core.models import PriceHistory, ProductType, Product, ModelScore, Model


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
                        ids_str = ','.join(str(id_) for id_ in ids_to_delete)
                        with db.connection() as conn:
                            conn.execute(text(f"DELETE FROM benefit_history WHERE product_id IN ({ids_str})"))
                            conn.execute(text(f"DELETE FROM price_history WHERE product_id IN ({ids_str})"))
                            conn.execute(text(f"DELETE FROM attribute_values WHERE product_id IN ({ids_str})"))
                            result = conn.execute(text(f"DELETE FROM products WHERE id IN ({ids_str})"))
                            conn.commit()
                        db.expire_all()
                        st.success(f"Удалено {result.rowcount} товаров.")
                        st.session_state[f"show_confirm_{key_suffix}"] = False
                        st.session_state[f"to_delete_{key_suffix}"] = []
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка удаления: {type(e).__name__}: {e}")
            with col2:
                if st.button("❌ Отмена", key=f"confirm_no_{key_suffix}"):
                    st.session_state[f"show_confirm_{key_suffix}"] = False
                    st.session_state[f"to_delete_{key_suffix}"] = []
                    st.rerun()


def render_diagnostic_tab(db: Session, type_name: str, type_id: int):
    """Отрисовывает вкладку для конкретного типа продукта."""
    # Проверяем, есть ли модели для этого типа (если тип поддерживает модели)
    has_models = db.query(Model).filter_by(type_id=type_id).first() is not None

    # Без характеристик
    products_no_attrs = db.query(Product).filter(
        Product.type_id == type_id,
        ~Product.attribute_values.any()
    ).all()
    if products_no_attrs:
        df = pd.DataFrame([(p.id, p.name, p.url) for p in products_no_attrs], columns=["ID", "Name", "URL"])
        render_problem_table(db, f"{type_name} – без характеристик", df, [p.id for p in products_no_attrs], f"{type_name.lower()}_no_attrs")
    else:
        st.success(f"✅ {type_name} – без характеристик: проблем нет!")

    # Без баллов (только если есть модели)
    if has_models:
        model_ids_with_scores = [row[0] for row in db.query(ModelScore.model_id).distinct().all()]
        products_no_scores = db.query(Product).filter(
            Product.type_id == type_id,
            Product.model_id.isnot(None),
            Product.model_id.notin_(model_ids_with_scores)
        ).all()
        if products_no_scores:
            df = pd.DataFrame([(p.id, p.name, p.model.name if p.model else "Нет модели", p.url)
                               for p in products_no_scores], columns=["ID", "Name", "Model Name", "URL"])
            render_problem_table(db, f"{type_name} – без баллов", df, [p.id for p in products_no_scores], f"{type_name.lower()}_no_scores")
        else:
            st.success(f"✅ {type_name} – без баллов: проблем нет!")

    # Без цены
    product_ids_with_price = [row[0] for row in db.query(PriceHistory.product_id).distinct().all()]
    products_no_price = db.query(Product).filter(
        Product.type_id == type_id,
        Product.id.notin_(product_ids_with_price)
    ).all()
    if products_no_price:
        df = pd.DataFrame([(p.id, p.name, p.url) for p in products_no_price], columns=["ID", "Name", "URL"])
        render_problem_table(db, f"{type_name} – без цены", df, [p.id for p in products_no_price], f"{type_name.lower()}_no_price")
    else:
        st.success(f"✅ {type_name} – без цены: проблем нет!")


def render(db: Session):
    # Получаем все типы продуктов, для которых есть хотя бы один продукт
    product_types = db.query(ProductType).order_by(ProductType.name).all()
    types_with_products = [
        pt for pt in product_types
        if db.query(Product).filter_by(type_id=pt.id).first() is not None
    ]

    if not types_with_products:
        st.info("Нет данных о типах продуктов в БД.")
        return

    # Создаём вкладки динамически
    tabs = st.tabs([pt.name for pt in types_with_products])
    for tab, pt in zip(tabs, types_with_products):
        with tab:
            render_diagnostic_tab(db, pt.name, pt.id)