import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from dnsight.core.models import (
    ProductType, Model, ModelScore, Product, Attribute,
    AttributeValue, PriceHistory, BenefitHistory
)


def render_table_with_data_editor(db: Session, table_name: str, query, id_column: str, display_columns: list, column_names: list = None):
    data = query.all()
    if not data:
        st.info(f"Нет данных в таблице {table_name}.")
        return

    rows = []
    for row in data:
        row_dict = {}
        for col in display_columns:
            if isinstance(col, str):
                val = getattr(row, col)
            else:
                val = col
            row_dict[col if isinstance(col, str) else str(col)] = val
        rows.append(row_dict)

    df = pd.DataFrame(rows)
    if column_names:
        df.columns = column_names

    delete_col = "🗑️ Удалить?"
    df.insert(0, delete_col, False)

    column_config = {
        delete_col: st.column_config.CheckboxColumn(label="", width=30, default=False),
    }

    edited_df = st.data_editor(
        df,
        column_config=column_config,
        width='stretch',
        hide_index=True,
        key=f"data_editor_{table_name}"
    )

    if st.button(f"🗑️ Удалить отмеченные", key=f"del_selected_{table_name}"):
        to_delete_mask = edited_df[delete_col] == True
        if to_delete_mask.any():
            id_col_name = df.columns[1]
            ids_to_delete = edited_df.loc[to_delete_mask, id_col_name].tolist()
            confirm = st.checkbox(str(f"Подтвердить удаление {len(ids_to_delete)} записей?"), key=f"confirm_{table_name}")
            if confirm:
                try:
                    model_class = query.column_descriptions[0]['type']
                    query.filter(getattr(model_class, id_column).in_(ids_to_delete)).delete(synchronize_session='fetch')
                    db.commit()
                    st.success(f"Удалено {len(ids_to_delete)} записей.")
                    st.rerun()
                except Exception as e:
                    db.rollback()
                    st.error(f"Ошибка удаления: {e}")
        else:
            st.info("Нет выбранных записей.")


def render(db: Session):
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
        ["product_types", "models", "model_scores", "products",
         "attributes", "attribute_values", "price_history", "benefit_history"]
    )

    with tab1:
        render_table_with_data_editor(db, "product_types", db.query(ProductType), "id",
                                      ["id", "name", "description"], ["id", "name", "description"])
    with tab2:
        render_table_with_data_editor(db, "models", db.query(Model), "id",
                                      ["id", "name", "type_id"], ["id", "name", "type_id"])
    with tab3:
        render_table_with_data_editor(db, "model_scores", db.query(ModelScore), "id",
                                      ["id", "model_id", "score", "source", "updated_at"],
                                      ["id", "model_id", "score", "source", "updated_at"])
    with tab4:
        render_table_with_data_editor(db, "products", db.query(Product), "id",
                                      ["id", "type_id", "model_id", "name", "url", "created_at", "updated_at"],
                                      ["id", "type_id", "model_id", "name", "url", "created_at", "updated_at"])
    with tab5:
        render_table_with_data_editor(db, "attributes", db.query(Attribute), "id",
                                      ["id", "name", "type_id"], ["id", "name", "type_id"])
    with tab6:
        render_table_with_data_editor(db, "attribute_values", db.query(AttributeValue), "id",
                                      ["id", "product_id", "attribute_id", "raw_value", "updated_at"],
                                      ["id", "product_id", "attribute_id", "raw_value", "updated_at"])
    with tab7:
        render_table_with_data_editor(db, "price_history", db.query(PriceHistory), "id",
                                      ["id", "product_id", "price", "timestamp"],
                                      ["id", "product_id", "price", "timestamp"])
    with tab8:
        render_table_with_data_editor(db, "benefit_history", db.query(BenefitHistory), "id",
                                      ["id", "product_id", "benefit", "timestamp"],
                                      ["id", "product_id", "benefit", "timestamp"])