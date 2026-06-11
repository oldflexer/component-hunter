import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import text
from dnsight.core.models import (
    ProductType, Model, ModelScore, Product, Attribute,
    AttributeValue, PriceHistory, BenefitHistory
)


def parse_id_input(id_input: str) -> list:
    """Преобразует строку вида '1,3-5,7' в список целых чисел [1,3,4,5,7]."""
    ids = set()
    parts = id_input.replace(' ', '').split(',')
    for part in parts:
        if not part:
            continue
        if '-' in part:
            start, end = part.split('-')
            if start.isdigit() and end.isdigit():
                ids.update(range(int(start), int(end) + 1))
        else:
            if part.isdigit():
                ids.add(int(part))
    return sorted(ids)


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

    # Кнопка для удаления отмеченных чекбоксами
    if st.button(f"🗑️ Удалить отмеченные", key=f"del_selected_{table_name}"):
        to_delete_mask = edited_df[delete_col] == True
        if to_delete_mask.any():
            id_col_name = df.columns[1]
            ids_to_delete = edited_df.loc[to_delete_mask, id_col_name].tolist()
            st.session_state[f"to_delete_{table_name}"] = ids_to_delete
            st.session_state[f"show_confirm_{table_name}"] = True
        else:
            st.info("Нет выбранных записей.")

    if st.session_state.get(f"show_confirm_{table_name}", False):
        ids_to_delete = st.session_state.get(f"to_delete_{table_name}", [])
        if ids_to_delete:
            st.warning(f"Вы собираетесь удалить {len(ids_to_delete)} записей из таблицы {table_name}. Это действие необратимо!")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Да, удалить", key=f"confirm_yes_{table_name}"):
                    try:
                        ids_str = ','.join(str(id_) for id_ in ids_to_delete)
                        with db.connection() as conn:
                            if table_name == "products":
                                conn.execute(text(f"DELETE FROM benefit_history WHERE product_id IN ({ids_str})"))
                                conn.execute(text(f"DELETE FROM price_history WHERE product_id IN ({ids_str})"))
                                conn.execute(text(f"DELETE FROM attribute_values WHERE product_id IN ({ids_str})"))
                                conn.execute(text(f"DELETE FROM products WHERE id IN ({ids_str})"))
                            elif table_name == "models":
                                conn.execute(text(f"DELETE FROM model_scores WHERE model_id IN ({ids_str})"))
                                conn.execute(text(f"DELETE FROM benefit_history WHERE product_id IN (SELECT id FROM products WHERE model_id IN ({ids_str}))"))
                                conn.execute(text(f"DELETE FROM price_history WHERE product_id IN (SELECT id FROM products WHERE model_id IN ({ids_str}))"))
                                conn.execute(text(f"DELETE FROM attribute_values WHERE product_id IN (SELECT id FROM products WHERE model_id IN ({ids_str}))"))
                                conn.execute(text(f"DELETE FROM products WHERE model_id IN ({ids_str})"))
                                conn.execute(text(f"DELETE FROM models WHERE id IN ({ids_str})"))
                            elif table_name == "product_types":
                                conn.execute(text(f"DELETE FROM model_scores WHERE model_id IN (SELECT id FROM models WHERE type_id IN ({ids_str}))"))
                                conn.execute(text(f"DELETE FROM benefit_history WHERE product_id IN (SELECT id FROM products WHERE type_id IN ({ids_str}))"))
                                conn.execute(text(f"DELETE FROM price_history WHERE product_id IN (SELECT id FROM products WHERE type_id IN ({ids_str}))"))
                                conn.execute(text(f"DELETE FROM attribute_values WHERE product_id IN (SELECT id FROM products WHERE type_id IN ({ids_str}))"))
                                conn.execute(text(f"DELETE FROM products WHERE type_id IN ({ids_str})"))
                                conn.execute(text(f"DELETE FROM models WHERE type_id IN ({ids_str})"))
                                conn.execute(text(f"DELETE FROM attribute_values WHERE attribute_id IN (SELECT id FROM attributes WHERE type_id IN ({ids_str}))"))
                                conn.execute(text(f"DELETE FROM attributes WHERE type_id IN ({ids_str})"))
                                conn.execute(text(f"DELETE FROM product_types WHERE id IN ({ids_str})"))
                            elif table_name == "attributes":
                                conn.execute(text(f"DELETE FROM attribute_values WHERE attribute_id IN ({ids_str})"))
                                conn.execute(text(f"DELETE FROM attributes WHERE id IN ({ids_str})"))
                            else:
                                conn.execute(text(f"DELETE FROM {table_name} WHERE {id_column} IN ({ids_str})"))
                            conn.commit()
                        db.expire_all()
                        st.success(f"Удалено {len(ids_to_delete)} записей.")
                        st.session_state[f"show_confirm_{table_name}"] = False
                        st.session_state[f"to_delete_{table_name}"] = []
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка удаления: {type(e).__name__}: {e}")
            with col2:
                if st.button("❌ Отмена", key=f"confirm_no_{table_name}"):
                    st.session_state[f"show_confirm_{table_name}"] = False
                    st.session_state[f"to_delete_{table_name}"] = []
                    st.rerun()

    # ---- Удаление по ID (диапазон) ----
    st.markdown("---")
    st.subheader("Удаление по ID")
    id_input = st.text_input("Введите ID (например: 1,3-5,7 или 10-20)", key=f"id_input_{table_name}")
    if st.button("🗑️ Удалить по ID", key=f"del_by_ids_{table_name}"):
        if id_input:
            ids_to_delete = parse_id_input(id_input)
            if not ids_to_delete:
                st.warning("Не удалось распознать ID. Используйте форматы: 1,2,3  или 1-5  или 1-5,7,9-12")
            else:
                st.session_state[f"ids_to_delete_{table_name}"] = ids_to_delete
                st.session_state[f"show_confirm_ids_{table_name}"] = True
        else:
            st.info("Введите ID для удаления.")

    # Подтверждение удаления по ID
    if st.session_state.get(f"show_confirm_ids_{table_name}", False):
        ids_to_delete = st.session_state.get(f"ids_to_delete_{table_name}", [])
        if ids_to_delete:
            st.warning(f"Вы собираетесь удалить {len(ids_to_delete)} записей из таблицы {table_name}. Это действие необратимо!")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Да, удалить", key=f"confirm_ids_yes_{table_name}"):
                    try:
                        ids_str = ','.join(str(id_) for id_ in ids_to_delete)
                        # Используем db.execute вместо ручного соединения
                        if table_name == "products":
                            db.execute(text(f"DELETE FROM benefit_history WHERE product_id IN ({ids_str})"))
                            db.execute(text(f"DELETE FROM price_history WHERE product_id IN ({ids_str})"))
                            db.execute(text(f"DELETE FROM attribute_values WHERE product_id IN ({ids_str})"))
                            db.execute(text(f"DELETE FROM products WHERE id IN ({ids_str})"))
                        elif table_name == "models":
                            db.execute(text(f"DELETE FROM model_scores WHERE model_id IN ({ids_str})"))
                            db.execute(text(f"DELETE FROM benefit_history WHERE product_id IN (SELECT id FROM products WHERE model_id IN ({ids_str}))"))
                            db.execute(text(f"DELETE FROM price_history WHERE product_id IN (SELECT id FROM products WHERE model_id IN ({ids_str}))"))
                            db.execute(text(f"DELETE FROM attribute_values WHERE product_id IN (SELECT id FROM products WHERE model_id IN ({ids_str}))"))
                            db.execute(text(f"DELETE FROM products WHERE model_id IN ({ids_str})"))
                            db.execute(text(f"DELETE FROM models WHERE id IN ({ids_str})"))
                        elif table_name == "product_types":
                            db.execute(text(f"DELETE FROM model_scores WHERE model_id IN (SELECT id FROM models WHERE type_id IN ({ids_str}))"))
                            db.execute(text(f"DELETE FROM benefit_history WHERE product_id IN (SELECT id FROM products WHERE type_id IN ({ids_str}))"))
                            db.execute(text(f"DELETE FROM price_history WHERE product_id IN (SELECT id FROM products WHERE type_id IN ({ids_str}))"))
                            db.execute(text(f"DELETE FROM attribute_values WHERE product_id IN (SELECT id FROM products WHERE type_id IN ({ids_str}))"))
                            db.execute(text(f"DELETE FROM products WHERE type_id IN ({ids_str})"))
                            db.execute(text(f"DELETE FROM models WHERE type_id IN ({ids_str})"))
                            db.execute(text(f"DELETE FROM attribute_values WHERE attribute_id IN (SELECT id FROM attributes WHERE type_id IN ({ids_str}))"))
                            db.execute(text(f"DELETE FROM attributes WHERE type_id IN ({ids_str})"))
                            db.execute(text(f"DELETE FROM product_types WHERE id IN ({ids_str})"))
                        elif table_name == "attributes":
                            db.execute(text(f"DELETE FROM attribute_values WHERE attribute_id IN ({ids_str})"))
                            db.execute(text(f"DELETE FROM attributes WHERE id IN ({ids_str})"))
                        else:
                            db.execute(text(f"DELETE FROM {table_name} WHERE {id_column} IN ({ids_str})"))
                        db.commit()
                        db.expire_all()
                        st.success(f"Удалено {len(ids_to_delete)} записей.")
                        # Сброс состояния
                        st.session_state[f"show_confirm_ids_{table_name}"] = False
                        st.session_state[f"ids_to_delete_{table_name}"] = []
                        st.rerun()
                    except Exception as e:
                        db.rollback()
                        st.error(f"Ошибка удаления: {type(e).__name__}: {e}")
            with col2:
                if st.button("❌ Отмена", key=f"confirm_ids_no_{table_name}"):
                    st.session_state[f"show_confirm_ids_{table_name}"] = False
                    st.session_state[f"ids_to_delete_{table_name}"] = []
                    st.rerun()


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