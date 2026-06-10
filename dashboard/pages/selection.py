import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from dnsight.core.models import ProductType, Model, Product
from dashboard.utils import get_last_score, get_last_price, get_last_benefit


def render(db: Session):
    sub_tab1, sub_tab2 = st.tabs(["Подбор GPU под CPU", "Подбор CPU под GPU"])

    # Подбор GPU под CPU
    with sub_tab1:
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
                # selected_cpu[2] гарантированно не None, так как мы отфильтровали
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

    # Подбор CPU под GPU
    with sub_tab2:
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