import streamlit as st
from datetime import datetime
from sqlalchemy.orm import Session
from dnsight.core.models import ProductType, Product, Attribute, AttributeValue, PriceHistory
from dashboard.utils import get_last_price


def edit_attributes(db: Session, component_type: str):
    type_obj = db.query(ProductType).filter_by(name=component_type).first()
    if not type_obj:
        st.warning(f"Тип {component_type} не найден в БД.")
        return
    products = db.query(Product).filter_by(type_id=type_obj.id).all()
    if not products:
        st.info(f"Нет продуктов типа {component_type}.")
        return

    product_names = {p.name: p.id for p in products}
    selected_name = st.selectbox(f"Выберите {component_type}", list(product_names.keys()))
    selected_id = product_names[selected_name]
    product = db.query(Product).filter_by(id=selected_id).first()

    # ----- Управление ценой -----
    current_price = get_last_price(db, selected_id)
    st.subheader("💰 Цена")
    col_price1, col_price2 = st.columns(2)
    with col_price1:
        st.metric("Текущая цена (₽)", f"{current_price:.0f}" if current_price else "Нет данных")
    with col_price2:
        new_price = st.number_input("Новая цена (₽)", min_value=0.0, step=10.0, value=0.0, key=f"price_{component_type}_{selected_id}")
        if new_price > 0 and new_price != current_price:
            if st.checkbox("Добавить новую цену в историю", key=f"add_price_{component_type}_{selected_id}"):
                price_history = PriceHistory(product_id=selected_id, price=new_price, timestamp=datetime.utcnow())
                db.add(price_history)
                db.commit()
                st.success(f"Цена {new_price:.0f} ₽ добавлена в историю!")
                st.rerun()
        elif new_price == current_price and current_price is not None:
            st.info("Новая цена совпадает с текущей, изменений не требуется.")

    # ----- Редактирование характеристик -----
    attrs = db.query(AttributeValue).filter_by(product_id=selected_id).all()
    attr_dict = {av.attribute.name: av.raw_value for av in attrs}

    st.subheader("Редактирование характеристик")
    attr_items = list(attr_dict.items())
    mid = (len(attr_items) + 1) // 2
    left_items = attr_items[:mid]
    right_items = attr_items[mid:]

    with st.form(key=f"edit_form_{component_type}"):
        col1, col2 = st.columns(2)
        new_attrs = {}

        with col1:
            for attr_name, current_value in left_items:
                new_val = st.text_input(f"{attr_name}", value=current_value, key=f"{component_type}_{attr_name}_left")
                new_attrs[attr_name] = new_val
        with col2:
            for attr_name, current_value in right_items:
                new_val = st.text_input(f"{attr_name}", value=current_value, key=f"{component_type}_{attr_name}_right")
                new_attrs[attr_name] = new_val

        st.markdown("---")
        new_attr_name = st.text_input("Название нового атрибута (оставьте пустым, если не нужно)")
        new_attr_value = st.text_input("Значение нового атрибута") if new_attr_name else ""

        submitted = st.form_submit_button("Сохранить изменения характеристик")
        if submitted:
            try:
                for attr_name, new_value in new_attrs.items():
                    attr = db.query(Attribute).filter_by(name=attr_name).first()
                    if attr:
                        av = db.query(AttributeValue).filter_by(product_id=selected_id, attribute_id=attr.id).first()
                        if av:
                            av.raw_value = new_value
                            av.updated_at = datetime.utcnow()
                if new_attr_name and new_attr_value:
                    attr = db.query(Attribute).filter_by(name=new_attr_name).first()
                    if not attr:
                        attr = Attribute(name=new_attr_name, type_id=type_obj.id)
                        db.add(attr)
                        db.flush()
                    av = AttributeValue(product_id=selected_id, attribute_id=attr.id, raw_value=new_attr_value)
                    db.add(av)
                db.commit()
                st.success("Характеристики обновлены!")
                st.rerun()
            except Exception as e:
                db.rollback()
                st.error(f"Ошибка сохранения: {e}")


def render(db: Session):
    form_tab1, form_tab2, form_tab3 = st.tabs(["CPU", "GPU", "Motherboard"])
    with form_tab1:
        edit_attributes(db, "CPU")
    with form_tab2:
        edit_attributes(db, "GPU")
    with form_tab3:
        edit_attributes(db, "Motherboard")