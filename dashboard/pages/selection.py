import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from dnsight.core.models import ProductType, Model, Product, Attribute, AttributeValue
from dashboard.utils import get_last_score, get_last_price, get_last_benefit


def render(db: Session):
    tabs = st.tabs(["Подбор GPU под CPU", "Подбор CPU под GPU", "Подбор CPU под MB", "Подбор MB под CPU"])

    # ---- Подбор GPU под CPU (существующий код) ----
    with tabs[0]:
        st.subheader("Выберите CPU, чтобы увидеть рекомендуемые GPU")
        cpu_type = db.query(ProductType).filter_by(name="CPU").first()
        gpu_type = db.query(ProductType).filter_by(name="GPU").first()
        if not cpu_type or not gpu_type:
            st.warning("Нет данных о CPU или GPU")
        else:
            cpu_models = db.query(Model).filter_by(type_id=cpu_type.id).all()
            cpu_list = []
            for model in cpu_models:
                score = get_last_score(db, model.id)
                if score is not None:
                    cpu_list.append((model.id, model.name, score))
            if not cpu_list:
                st.info("Нет CPU с баллами PassMark")
            else:
                selected_cpu_name = st.selectbox("Выберите CPU", [c[1] for c in cpu_list], key="cpu_select")
                selected_cpu = next(c for c in cpu_list if c[1] == selected_cpu_name)
                target_gpu_score = selected_cpu[2] * 1.25
                st.info(f"Целевой балл GPU: {target_gpu_score:.0f}")

                gpu_models = db.query(Model).filter_by(type_id=gpu_type.id).all()
                gpu_data = []
                for model in gpu_models:
                    score = get_last_score(db, model.id)
                    if score is None:
                        continue
                    product = db.query(Product).filter_by(model_id=model.id).first()
                    price = get_last_price(db, product.id) if product else None
                    benefit = get_last_benefit(db, product.id) if product else None
                    gpu_data.append({
                        "Model Name": model.name,
                        "Score": score,
                        "Price (RUB)": price if price is not None else 0,
                        "Benefit": benefit if benefit is not None else 0,
                        "Deviation": abs(score - target_gpu_score) / target_gpu_score if target_gpu_score > 0 else 999
                    })
                df = pd.DataFrame(gpu_data)
                if not df.empty:
                    max_benefit = df['Benefit'].max()
                    if max_benefit > 0:
                        df['Benefit %'] = (df['Benefit'] / max_benefit * 100).round(1)
                    else:
                        df['Benefit %'] = 0
                    df = df.sort_values(by="Deviation")
                    df["Match"] = df["Deviation"].apply(
                        lambda x: "⭐ Оптимально" if x < 0.2 else "👍 Хорошо" if x < 0.4 else "⚠️ Слабоват" if x > 0.6 else "👌 Приемлемо"
                    )
                    st.dataframe(df[["Model Name", "Score", "Price (RUB)", "Benefit", "Benefit %", "Match"]], width='stretch')

    # ---- Подбор CPU под GPU (существующий код) ----
    with tabs[1]:
        st.subheader("Выберите GPU, чтобы увидеть рекомендуемые CPU")
        gpu_type = db.query(ProductType).filter_by(name="GPU").first()
        cpu_type = db.query(ProductType).filter_by(name="CPU").first()
        if not gpu_type or not cpu_type:
            st.warning("Нет данных о GPU или CPU")
        else:
            gpu_models = db.query(Model).filter_by(type_id=gpu_type.id).all()
            gpu_list = []
            for model in gpu_models:
                score = get_last_score(db, model.id)
                if score is not None:
                    gpu_list.append((model.id, model.name, score))
            if not gpu_list:
                st.info("Нет GPU с баллами PassMark")
            else:
                selected_gpu_name = st.selectbox("Выберите GPU", [g[1] for g in gpu_list], key="gpu_select")
                selected_gpu = next(g for g in gpu_list if g[1] == selected_gpu_name)
                target_cpu_score = selected_gpu[2] / 1.25
                st.info(f"Целевой балл CPU: {target_cpu_score:.0f}")

                cpu_models = db.query(Model).filter_by(type_id=cpu_type.id).all()
                cpu_data = []
                for model in cpu_models:
                    score = get_last_score(db, model.id)
                    if score is None:
                        continue
                    product = db.query(Product).filter_by(model_id=model.id).first()
                    price = get_last_price(db, product.id) if product else None
                    benefit = get_last_benefit(db, product.id) if product else None
                    cpu_data.append({
                        "Model Name": model.name,
                        "Score": score,
                        "Price (RUB)": price if price is not None else 0,
                        "Benefit": benefit if benefit is not None else 0,
                        "Deviation": abs(score - target_cpu_score) / target_cpu_score if target_cpu_score > 0 else 999
                    })
                df = pd.DataFrame(cpu_data)
                if not df.empty:
                    max_benefit = df['Benefit'].max()
                    if max_benefit > 0:
                        df['Benefit %'] = (df['Benefit'] / max_benefit * 100).round(1)
                    else:
                        df['Benefit %'] = 0
                    df = df.sort_values(by="Deviation")
                    df["Match"] = df["Deviation"].apply(
                        lambda x: "⭐ Оптимально" if x < 0.2 else "👍 Хорошо" if x < 0.4 else "⚠️ Слабоват" if x > 0.6 else "👌 Приемлемо"
                    )
                    st.dataframe(df[["Model Name", "Score", "Price (RUB)", "Benefit", "Benefit %", "Match"]], width='stretch')

    # ---- Подбор CPU под MB ----
    with tabs[2]:
        st.subheader("Выберите материнскую плату, чтобы увидеть совместимые CPU")
        mb_type = db.query(ProductType).filter_by(name="Motherboard").first()
        cpu_type = db.query(ProductType).filter_by(name="CPU").first()
        if not mb_type or not cpu_type:
            st.warning("Нет данных о MB или CPU")
        else:
            mb_products = db.query(Product).filter_by(type_id=mb_type.id).all()
            mb_list = []
            for prod in mb_products:
                attrs = db.query(AttributeValue).filter_by(product_id=prod.id).all()
                attr_dict = {av.attribute.name: av.raw_value for av in attrs}
                socket = attr_dict.get("Сокет")
                if socket:
                    mb_list.append((prod.id, prod.name, socket.strip()))
            if not mb_list:
                st.info("Нет MB с указанным сокетом")
            else:
                selected_mb_name = st.selectbox("Выберите материнскую плату", [m[1] for m in mb_list], key="mb_select")
                selected_mb = next(m for m in mb_list if m[1] == selected_mb_name)
                socket = selected_mb[2]
                st.info(f"Сокет: {socket}")

                cpu_models = db.query(Model).filter_by(type_id=cpu_type.id).all()
                compatible_cpu = []
                for model in cpu_models:
                    prod = db.query(Product).filter_by(model_id=model.id).first()
                    if not prod:
                        continue
                    attrs = db.query(AttributeValue).filter_by(product_id=prod.id).all()
                    attr_dict = {av.attribute.name: av.raw_value for av in attrs}
                    cpu_socket = attr_dict.get("Сокет")
                    if cpu_socket and cpu_socket.strip() == socket:
                        score = get_last_score(db, model.id)
                        if score:
                            price = get_last_price(db, prod.id)
                            benefit = get_last_benefit(db, prod.id) or 0.0
                            compatible_cpu.append({
                                "Model Name": model.name,
                                "Score": score,
                                "Price (RUB)": price if price else 0,
                                "Benefit": benefit,
                            })
                if compatible_cpu:
                    df = pd.DataFrame(compatible_cpu)
                    max_benefit = df['Benefit'].max()
                    if max_benefit > 0:
                        df['Benefit %'] = (df['Benefit'] / max_benefit * 100).round(1)
                    else:
                        df['Benefit %'] = 0
                    df = df.sort_values(by="Benefit", ascending=False)
                    st.dataframe(df[["Model Name", "Score", "Price (RUB)", "Benefit", "Benefit %"]], width='stretch')
                else:
                    st.info("Нет совместимых CPU")

    # ---- Подбор MB под CPU ----
    with tabs[3]:
        st.subheader("Выберите процессор, чтобы увидеть совместимые материнские платы")
        cpu_type = db.query(ProductType).filter_by(name="CPU").first()
        mb_type = db.query(ProductType).filter_by(name="Motherboard").first()
        if not cpu_type or not mb_type:
            st.warning("Нет данных о CPU или MB")
        else:
            cpu_models = db.query(Model).filter_by(type_id=cpu_type.id).all()
            cpu_list = []
            for model in cpu_models:
                score = get_last_score(db, model.id)
                if score:
                    prod = db.query(Product).filter_by(model_id=model.id).first()
                    if prod:
                        attrs = db.query(AttributeValue).filter_by(product_id=prod.id).all()
                        attr_dict = {av.attribute.name: av.raw_value for av in attrs}
                        socket = attr_dict.get("Сокет")
                        if socket:
                            cpu_list.append((model.id, model.name, socket.strip(), score))
            if not cpu_list:
                st.info("Нет CPU с сокетом")
            else:
                selected_cpu_name = st.selectbox("Выберите CPU", [c[1] for c in cpu_list], key="cpu_select_mb")
                selected_cpu = next(c for c in cpu_list if c[1] == selected_cpu_name)
                socket = selected_cpu[2]
                st.info(f"Сокет: {socket}")

                mb_products = db.query(Product).filter_by(type_id=mb_type.id).all()
                compatible_mb = []
                for prod in mb_products:
                    attrs = db.query(AttributeValue).filter_by(product_id=prod.id).all()
                    attr_dict = {av.attribute.name: av.raw_value for av in attrs}
                    mb_socket = attr_dict.get("Сокет")
                    if mb_socket and mb_socket.strip() == socket:
                        price = get_last_price(db, prod.id)
                        if price:
                            benefit = get_last_benefit(db, prod.id) or 0.0
                            model_name = prod.model.name if prod.model else attr_dict.get("Модель", "")
                            compatible_mb.append({
                                "Model Name": model_name,
                                "Price (RUB)": price,
                                "Benefit": benefit,
                            })
                if compatible_mb:
                    df = pd.DataFrame(compatible_mb)
                    max_benefit = df['Benefit'].max()
                    if max_benefit > 0:
                        df['Benefit %'] = (df['Benefit'] / max_benefit * 100).round(1)
                    else:
                        df['Benefit %'] = 0
                    df = df.sort_values(by="Benefit", ascending=False)
                    st.dataframe(df[["Model Name", "Price (RUB)", "Benefit", "Benefit %"]], width='stretch')
                else:
                    st.info("Нет совместимых MB")