import streamlit as st
from datetime import datetime
from sqlalchemy.orm import Session
from dnsight.core.models import ProductType, Product, Attribute, AttributeValue


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

    attrs = db.query(AttributeValue).filter_by(product_id=selected_id).all()
    attr_dict = {av.attribute.name: av.raw_value for av in attrs}

    st.subheader("Редактирование характеристик")
    with st.form(key=f"edit_form_{component_type}"):
        new_attrs = {}
        for attr_name, current_value in attr_dict.items():
            new_val = st.text_input(f"{attr_name}", value=current_value, key=f"{component_type}_{attr_name}")
            new_attrs[attr_name] = new_val

        new_attr_name = st.text_input("Название нового атрибута (оставьте пустым, если не нужно)")
        new_attr_value = st.text_input("Значение нового атрибута") if new_attr_name else ""

        submitted = st.form_submit_button("Сохранить изменения")
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
    form_tab1, form_tab2 = st.tabs(["CPU", "GPU"])
    with form_tab1:
        edit_attributes(db, "CPU")
    with form_tab2:
        edit_attributes(db, "GPU")