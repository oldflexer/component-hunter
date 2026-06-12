import math
import re

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


# ---- Данные для CPU × MB (общие: сокет, score, benefit) ----
def extract_pcie_version(pcie_str: str) -> float:
    if not pcie_str:
        return 0.0
    match = re.search(r'(\d+\.?\d*)', pcie_str)
    return float(match.group(1)) if match else 0.0


def extract_first_number(value: str) -> int:
    match = re.search(r'\d+', value)
    return int(match.group()) if match else 0


def extract_tdp(value: str) -> int:
    match = re.search(r'\d+', value)
    return int(match.group()) if match else 0


@st.cache_data(ttl=3600, hash_funcs={Session: lambda _: None})
def get_cpu_socket_pcie(db: Session):
    cpu_type = db.query(ProductType).filter_by(name="CPU").first()
    if not cpu_type:
        return []
    cpu_models = db.query(Model).filter_by(type_id=cpu_type.id).all()
    cpu_list = []
    for model in cpu_models:
        score = get_last_score(db, model.id)
        if score is None:
            continue
        product = db.query(Product).filter_by(model_id=model.id).first()
        if not product:
            continue
        benefit = get_last_benefit(db, product.id) or 0.0
        attrs = db.query(AttributeValue).filter_by(product_id=product.id).all()
        attr_dict = {av.attribute.name: av.raw_value for av in attrs}
        socket = attr_dict.get("Сокет")
        pcie_raw = attr_dict.get("Встроенный контроллер PCI Express")
        pcie = extract_pcie_version(pcie_raw) if pcie_raw else 0.0
        tdp_raw = attr_dict.get("Тепловыделение (TDP)")
        tdp = extract_tdp(tdp_raw) if tdp_raw else 0
        if not socket:
            continue
        cpu_list.append({
            "name": model.name,
            "benefit": benefit,
            "score": score,
            "socket": socket.strip(),
            "pcie": pcie,
            "tdp": tdp,
        })
    socket_max_score = {}
    for cpu in cpu_list:
        s = cpu["socket"]
        if s not in socket_max_score or cpu["score"] > socket_max_score[s]:
            socket_max_score[s] = cpu["score"]
    sorted_sockets = sorted(socket_max_score.keys(), key=lambda s: socket_max_score[s], reverse=True)
    socket_order = {s: i for i, s in enumerate(sorted_sockets)}
    cpu_list.sort(key=lambda x: (socket_order[x["socket"]], -x["score"]))
    return cpu_list


@st.cache_data(ttl=3600, hash_funcs={Session: lambda _: None})
def get_mb_socket_pcie(db: Session):
    mb_type = db.query(ProductType).filter_by(name="Motherboard").first()
    if not mb_type:
        return []
    mb_products = db.query(Product).filter_by(type_id=mb_type.id).all()
    mb_list = []
    for prod in mb_products:
        benefit = get_last_benefit(db, prod.id) or 0.0
        score = 0.0
        if prod.model_id:
            score = get_last_score(db, prod.model_id) or 0.0
        attrs = db.query(AttributeValue).filter_by(product_id=prod.id).all()
        attr_dict = {av.attribute.name: av.raw_value for av in attrs}
        socket = attr_dict.get("Сокет")
        pcie_raw = attr_dict.get("Версия PCI Express")
        pcie = extract_pcie_version(pcie_raw) if pcie_raw else 0.0
        phase_raw = attr_dict.get("Количество фаз питания")
        phase = extract_first_number(phase_raw) if phase_raw else 0
        if not socket:
            continue

        display_name = None
        if prod.model_id:
            model = db.query(Model).filter_by(id=prod.model_id).first()
            if model:
                display_name = model.name
        if not display_name:
            display_name = attr_dict.get("Модель")
        if not display_name:
            display_name = prod.name

        mb_list.append({
            "name": display_name,
            "benefit": benefit,
            "score": score,
            "socket": socket.strip(),
            "pcie": pcie,
            "phase": phase,
        })
    cpu_sorted = get_cpu_socket_pcie(db)
    socket_order = {}
    for cpu in cpu_sorted:
        s = cpu["socket"]
        if s not in socket_order:
            socket_order[s] = len(socket_order)
    mb_list.sort(key=lambda x: (socket_order.get(x["socket"], len(socket_order)), -x["score"]))
    return mb_list


# --- Матричные вычисления ---
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
                val = (1 / diff) ** (1/2) if diff != 0 else float('inf')
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


@st.cache_data(ttl=3600, hash_funcs={Session: lambda _: None})
def compute_heatmap_cpu_mb_benefit(db: Session):
    cpus = get_cpu_socket_pcie(db)
    mbs = get_mb_socket_pcie(db)
    if not cpus or not mbs:
        return None, None, None
    cpu_names = [c["name"] for c in cpus]
    mb_names = [m["name"] for m in mbs]
    matrix = []
    for cpu in cpus:
        row = []
        for mb in mbs:
            if cpu["socket"] == mb["socket"]:
                row.append(cpu["benefit"] * mb["benefit"])
            else:
                row.append(None)
        matrix.append(row)
    return cpu_names, mb_names, matrix


@st.cache_data(ttl=3600, hash_funcs={Session: lambda _: None})
def compute_heatmap_power(db: Session):
    cpus = get_cpu_socket_pcie(db)
    mbs = get_mb_socket_pcie(db)
    if not cpus or not mbs:
        return None, None, None
    cpu_names = [c["name"] for c in cpus]
    mb_names = [m["name"] for m in mbs]
    matrix = []
    for cpu in cpus:
        row = []
        tdp = cpu["tdp"]
        if tdp == 0:
            row = [None] * len(mbs)
            matrix.append(row)
            continue
        for mb in mbs:
            if cpu["socket"] != mb["socket"]:
                row.append(None)
                continue
            phase = mb["phase"]
            if phase == 0:
                row.append(None)
                continue
            diff = abs((tdp / 10.58 - phase) ** (1 / 2))
            if diff == 0:
                val = 1
            else:
                val = (1.0 / diff) ** (1 / 2)
            row.append(val)
        matrix.append(row)
    return cpu_names, mb_names, matrix


@st.cache_data(ttl=3600, hash_funcs={Session: lambda _: None})
def compute_heatmap_combined_cpu_mb(db: Session):
    """Кривая подбора CPU×MB = sqrt(Benefit_CPU_MB * Power_CPU_MB)"""
    result_benefit = compute_heatmap_cpu_mb_benefit(db)
    result_power = compute_heatmap_power(db)
    if result_benefit is None or result_power is None:
        return None, None, None
    cpu_names_benefit, mb_names_benefit, benefit_mat = result_benefit
    cpu_names_power, mb_names_power, power_mat = result_power
    if (cpu_names_benefit is None or cpu_names_power is None or
        mb_names_benefit is None or mb_names_power is None):
        return None, None, None
    # Проверка, что матрицы существуют и не являются None
    if benefit_mat is None or power_mat is None:
        return None, None, None
    # Проверка, что матрицы не пустые
    if not benefit_mat or not power_mat:
        return None, None, None
    # Проверка совпадения размеров
    if len(benefit_mat) != len(power_mat) or (len(benefit_mat) > 0 and len(benefit_mat[0]) != len(power_mat[0])):
        return None, None, None
    combined = []
    for i in range(len(benefit_mat)):
        row = []
        for j in range(len(benefit_mat[0])):
            b = benefit_mat[i][j]
            p = power_mat[i][j]
            if b is None or p is None:
                row.append(None)
            else:
                row.append((b * p) ** (1 / 1))
        combined.append(row)
    return cpu_names_benefit, mb_names_benefit, combined


# --- Рендеринг ---
def render(db: Session):
    tabs = st.tabs([
        "📊 Benefit CPU × GPU",
        "🎯 Оптимальность CPU и GPU",
        "🔗 Кривая подбора CPU и GPU",
        "📊 Benefit CPU × MB",
        "⚡ Power CPU и MB",
        "🔗 Кривая подбора CPU и MB"
    ])

    # Benefit CPU × GPU
    with tabs[0]:
        cpu_names, gpu_names, raw_mat = compute_heatmap_benefit(db)
        if cpu_names is None:
            st.warning("Недостаточно данных для Benefit (CPU × GPU).")
        else:
            norm_mat = normalize_matrix(raw_mat)
            fig = px.imshow(norm_mat, x=gpu_names, y=cpu_names,
                            labels=dict(x="GPU (чип)", y="CPU (модель)", color="Benefit (норм.)"),
                            title="Тепловая карта: Benefit_CPU × Benefit_GPU",
                            color_continuous_scale="Plasma", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')

    # Оптимальность CPU и GPU
    with tabs[1]:
        cpu_names, gpu_names, raw_mat = compute_heatmap_optimal(db)
        if cpu_names is None:
            st.warning("Недостаточно данных для Оптимальности (CPU × GPU).")
        else:
            norm_mat = normalize_matrix(raw_mat)
            fig = px.imshow(norm_mat, x=gpu_names, y=cpu_names,
                            labels=dict(x="GPU (чип)", y="CPU (модель)", color="Оптимальность (норм.)"),
                            title="Тепловая карта: (1/|Score_CPU×1.25 - Score_GPU|)¹/²",
                            color_continuous_scale="Plasma", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')

    # Кривая подбора CPU и GPU
    with tabs[2]:
        cpu_names, gpu_names, raw_mat = compute_heatmap_combined(db)
        if cpu_names is None:
            st.warning("Недостаточно данных для Кривой подбора (CPU × GPU).")
        else:
            norm_mat = normalize_matrix(raw_mat)
            fig = px.imshow(norm_mat, x=gpu_names, y=cpu_names,
                            labels=dict(x="GPU (чип)", y="CPU (модель)", color="Кривая (норм.)"),
                            title="Тепловая карта: √(Benefit × Оптимальность)",
                            color_continuous_scale="Plasma", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')

    # Benefit CPU × MB
    with tabs[3]:
        cpu_names, mb_names, raw_mat = compute_heatmap_cpu_mb_benefit(db)
        if cpu_names is None:
            st.warning("Недостаточно данных для Benefit (CPU × MB). Убедитесь, что у CPU и MB заполнен сокет.")
        else:
            norm_mat = normalize_matrix(raw_mat)
            fig = px.imshow(norm_mat, x=mb_names, y=cpu_names,
                            labels=dict(x="Motherboard", y="CPU (модель)", color="Benefit (норм.)"),
                            title="Тепловая карта: Benefit_CPU × Benefit_MB (совместимые по сокету)",
                            color_continuous_scale="Plasma", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')

    # Power CPU и MB
    with tabs[4]:
        cpu_names, mb_names, raw_mat = compute_heatmap_power(db)
        if cpu_names is None:
            st.warning("Недостаточно данных для Power (CPU × MB). Убедитесь, что у CPU указан TDP, а у MB – количество фаз питания.")
        else:
            norm_mat = normalize_matrix(raw_mat)
            fig = px.imshow(norm_mat, x=mb_names, y=cpu_names,
                            labels=dict(x="Motherboard", y="CPU (модель)", color="Power (норм.)"),
                            title="Тепловая карта: √( 1 / √(|TDP·10.58/32.5 - Phase·32.5/10.58|) )",
                            color_continuous_scale="Plasma", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')

    # Кривая подбора CPU и MB
    with tabs[5]:
        cpu_names, mb_names, raw_mat = compute_heatmap_combined_cpu_mb(db)
        if cpu_names is None:
            st.warning("Недостаточно данных для Кривой подбора (CPU × MB). Убедитесь, что доступны данные Benefit и Power.")
        else:
            norm_mat = normalize_matrix(raw_mat)
            fig = px.imshow(norm_mat, x=mb_names, y=cpu_names,
                            labels=dict(x="Motherboard", y="CPU (модель)", color="Кривая (норм.)"),
                            title="Тепловая карта: √(Benefit_CPU_MB × Power_CPU_MB)",
                            color_continuous_scale="Plasma", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')