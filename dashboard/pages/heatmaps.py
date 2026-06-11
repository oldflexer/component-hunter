import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from dnsight.core.models import ProductType, Model, Product, Attribute, AttributeValue, ModelScore, BenefitHistory
from dashboard.utils import get_last_score, get_last_benefit, get_delta_ratio, normalize_matrix


# --- Вспомогательные функции для получения данных (с кэшированием) ---
@st.cache_data(ttl=3600, hash_funcs={Session: lambda _: None})
def get_cpu_models_data(db: Session):
    cpu_type = db.query(ProductType).filter_by(name="CPU").first()
    if not cpu_type:
        return []
    cpu_models = db.query(Model).filter_by(type_id=cpu_type.id).all()
    cpu_data = []
    for model in cpu_models:
        score = get_last_score(db, model.id)
        if score is None:
            continue
        product = db.query(Product).filter_by(model_id=model.id).first()
        benefit = get_last_benefit(db, product.id) if product else 0.0
        cpu_data.append({
            "id": model.id,
            "name": model.name,
            "score": score,
            "benefit": benefit
        })
    cpu_data.sort(key=lambda x: x["score"], reverse=True)
    return cpu_data


@st.cache_data(ttl=3600, hash_funcs={Session: lambda _: None})
def get_gpu_raw_values_data(db: Session):
    gpu_attr = db.query(Attribute).filter_by(name="Графический процессор").first()
    if not gpu_attr:
        return []
    raw_values = db.query(AttributeValue.raw_value).filter_by(attribute_id=gpu_attr.id).distinct().all()
    raw_values = [rv[0] for rv in raw_values if rv[0]]
    result = []
    for raw_val in raw_values:
        product_ids = db.query(AttributeValue.product_id).filter(
            AttributeValue.attribute_id == gpu_attr.id,
            AttributeValue.raw_value == raw_val
        ).distinct().all()
        product_ids = [pid[0] for pid in product_ids]
        if not product_ids:
            continue
        model_ids = db.query(Product.model_id).filter(
            Product.id.in_(product_ids),
            Product.model_id.isnot(None)
        ).distinct().all()
        model_ids = [mid[0] for mid in model_ids]
        best_score = None
        for mid in model_ids:
            ms = db.query(ModelScore).filter_by(model_id=mid).order_by(ModelScore.updated_at.desc()).first()
            if ms and ms.score is not None and (best_score is None or ms.score > best_score):
                best_score = ms.score
        if best_score is None:
            continue
        best_benefit = 0.0
        for pid in product_ids:
            bh = db.query(BenefitHistory).filter_by(product_id=pid).order_by(BenefitHistory.timestamp.desc()).first()
            if bh and bh.benefit is not None and bh.benefit > best_benefit:
                best_benefit = bh.benefit
        result.append({
            "name": raw_val,
            "score": best_score,
            "benefit": best_benefit
        })
    result.sort(key=lambda x: x["score"], reverse=True)
    return result


# --- Матричные вычисления (с кэшированием) ---
@st.cache_data(ttl=3600, hash_funcs={Session: lambda _: None})
def compute_heatmap_benefit(db: Session):
    cpus = get_cpu_models_data(db)
    gpus = get_gpu_raw_values_data(db)
    if not cpus or not gpus:
        return None, None, None
    cpu_names = [c["name"] for c in cpus]
    gpu_names = [g["name"] for g in gpus]
    matrix = []
    for cpu in cpus:
        row = []
        for gpu in gpus:
            row.append(cpu["benefit"] * gpu["benefit"])
        matrix.append(row)
    return cpu_names, gpu_names, matrix


@st.cache_data(ttl=3600, hash_funcs={Session: lambda _: None})
def compute_heatmap_optimal(db: Session):
    cpus = get_cpu_models_data(db)
    gpus = get_gpu_raw_values_data(db)
    if not cpus or not gpus:
        return None, None, None
    cpu_names = [c["name"] for c in cpus]
    gpu_names = [g["name"] for g in gpus]
    matrix = []
    for cpu in cpus:
        row = []
        cpu_score = cpu["score"]
        if cpu_score is None or cpu_score <= 0:
            row = [0.0] * len(gpus)
            matrix.append(row)
            continue
        target = cpu_score * 1.25
        for gpu in gpus:
            gpu_score = gpu["score"]
            if gpu_score is None:
                val = 0.0
            else:
                diff = abs(target - gpu_score)
                val = 1.0 / diff if diff != 0 else float('inf')
            row.append(val)
        matrix.append(row)
    return cpu_names, gpu_names, matrix


@st.cache_data(ttl=3600, hash_funcs={Session: lambda _: None})
def compute_heatmap_combined(db: Session):
    res_benefit = compute_heatmap_benefit(db)
    res_optimal = compute_heatmap_optimal(db)
    if res_benefit is None or res_optimal is None:
        return None, None, None
    if res_benefit[0] is None or res_optimal[0] is None:
        return None, None, None
    cpu_names, gpu_names = res_benefit[0], res_benefit[1]
    benefit_mat = res_benefit[2]
    optimal_mat = res_optimal[2]
    combined = []
    for i in range(len(cpu_names)):
        row = []
        for j in range(len(gpu_names)):
            row.append((benefit_mat[i][j] * optimal_mat[i][j]) ** (1/2))
        combined.append(row)
    return cpu_names, gpu_names, combined


# --- Рендеринг ---
def render(db: Session):
    tabs = st.tabs(["📊 Benefit (модели)", "🎯 Оптимальность (модели)", "🔗 Кривая подбора (модели)"])

    # Benefit
    with tabs[0]:
        cpu_names, gpu_names, raw_mat = compute_heatmap_benefit(db)
        if cpu_names is None:
            st.warning("Недостаточно данных для Benefit (модели).")
        else:
            norm_mat = normalize_matrix(raw_mat)
            fig = px.imshow(norm_mat, x=gpu_names, y=cpu_names,
                            labels=dict(x="GPU (чип)", y="CPU (модель)", color="Benefit (норм.)"),
                            title="Тепловая карта: Benefit_CPU × Benefit_GPU",
                            color_continuous_scale="Plasma", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')

    # Оптимальность
    with tabs[1]:
        cpu_names, gpu_names, raw_mat = compute_heatmap_optimal(db)
        if cpu_names is None:
            st.warning("Недостаточно данных для Оптимальности (модели).")
        else:
            norm_mat = normalize_matrix(raw_mat)
            fig = px.imshow(norm_mat, x=gpu_names, y=cpu_names,
                            labels=dict(x="GPU (чип)", y="CPU (модель)", color="Оптимальность (норм.)"),
                            title="Тепловая карта: 1/|Score_CPU×1.25 - Score_GPU|",
                            color_continuous_scale="Plasma", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')

    # Кривая подбора
    with tabs[2]:
        cpu_names, gpu_names, raw_mat = compute_heatmap_combined(db)
        if cpu_names is None:
            st.warning("Недостаточно данных для Кривой подбора (модели).")
        else:
            norm_mat = normalize_matrix(raw_mat)
            fig = px.imshow(norm_mat, x=gpu_names, y=cpu_names,
                            labels=dict(x="GPU (чип)", y="CPU (модель)", color="Кривая (норм.)"),
                            title="Тепловая карта: (Benefit × Динамика × Оптимальность)⅓",
                            color_continuous_scale="Plasma", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')