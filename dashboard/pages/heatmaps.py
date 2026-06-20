import math
import re
from concurrent.futures import ThreadPoolExecutor

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from dnsight.core.models import ProductType, Model, Product, Attribute, AttributeValue, ModelScore, BenefitHistory
from dashboard.utils import normalize_matrix, get_last_score, get_last_benefit, get_delta_ratio
from dnsight.services.component_service import ComponentService
from dnsight.services.heatmap_service import HeatmapService
from dnsight.config.settings import GPU_TARGET_MULTIPLIER, CACHE_TTL, TDP_PHASE_RATIO


# --- Функции получения компонентов (без кэширования, но с сортировкой) ---
def get_cpu_components(db: Session):
    service = ComponentService(db)
    cpus = service.get_cpu_components()
    cpus.sort(key=lambda cpu: cpu.get_score() if cpu.get_score() is not None else 0, reverse=True)
    return cpus

def get_gpu_components(db: Session):
    service = ComponentService(db)
    gpus = service.get_gpu_components()
    gpus.sort(key=lambda gpu: gpu.get_score() if gpu.get_score() is not None else 0, reverse=True)
    return gpus

def get_mb_components(db: Session):
    service = ComponentService(db)
    return service.get_mb_components()


# --- Кэшируемые функции для CPU/MB (сериализуемые данные) ---
@st.cache_data(ttl=CACHE_TTL, hash_funcs={Session: lambda _: None})
def get_cpu_socket_pcie(db: Session):
    """Возвращает список процессоров с сокетом, версией PCIe и TDP (используется в MB‑вкладках)"""
    cpus = get_cpu_components(db)
    result = []
    for cpu in cpus:
        socket = cpu.get_socket()
        if not socket:
            continue
        result.append({
            "name": cpu.name,
            "benefit": cpu.get_benefit(),
            "score": cpu.get_score(),
            "socket": socket,
            "pcie": cpu.get_pcie_version(),
            "tdp": cpu.get_tdp() if hasattr(cpu, "get_tdp") else 0,
        })
    socket_max_score = {}
    for c in result:
        s = c["socket"]
        if s not in socket_max_score or c["score"] > socket_max_score[s]:
            socket_max_score[s] = c["score"]
    sorted_sockets = sorted(socket_max_score.keys(), key=lambda s: socket_max_score[s], reverse=True)
    socket_order = {s: i for i, s in enumerate(sorted_sockets)}
    result.sort(key=lambda x: (socket_order[x["socket"]], -x["score"]))
    return result


@st.cache_data(ttl=CACHE_TTL, hash_funcs={Session: lambda _: None})
def get_mb_socket_pcie(db: Session):
    """Возвращает список материнских плат с сокетом, версией PCIe и количеством фаз"""
    mbs = get_mb_components(db)
    result = []
    for mb in mbs:
        socket = mb.get_socket()
        if not socket:
            continue
        result.append({
            "name": mb.name,
            "benefit": mb.get_benefit(),
            "score": mb.get_score(),
            "socket": socket,
            "pcie": mb.get_pcie_version(),
            "phase": mb.get_phase() if hasattr(mb, "get_phase") else 0,
        })
    cpu_sorted = get_cpu_socket_pcie(db)
    socket_order = {s: i for i, s in enumerate([c["socket"] for c in cpu_sorted])}
    result.sort(key=lambda x: (socket_order.get(x["socket"], len(socket_order)), -x["score"]))
    return result


# --- Кэшируемые матричные вычисления ---
@st.cache_data(ttl=CACHE_TTL, hash_funcs={Session: lambda _: None})
def compute_heatmap_benefit(db: Session):
    cpus = get_cpu_components(db)
    gpus = get_gpu_components(db)
    if not cpus or not gpus:
        return None, None, None
    cpu_names, gpu_names, matrix = HeatmapService.build_matrix(cpus, gpus, lambda cpu, gpu: cpu.get_benefit() * gpu.get_benefit())
    return cpu_names, gpu_names, matrix


@st.cache_data(ttl=CACHE_TTL, hash_funcs={Session: lambda _: None})
def compute_heatmap_optimal(db: Session):
    cpus = get_cpu_components(db)
    gpus = get_gpu_components(db)
    if not cpus or not gpus:
        return None, None, None
    def optimal_func(cpu, gpu):
        cpu_score = cpu.get_score()
        if cpu_score is None or cpu_score <= 0:
            return 0.0
        target = cpu_score * GPU_TARGET_MULTIPLIER
        gpu_score = gpu.get_score()
        if gpu_score is None:
            return 0.0
        diff = abs(target - gpu_score)
        return (1 / diff) ** 0.5 if diff != 0 else float('inf')
    cpu_names, gpu_names, matrix = HeatmapService.build_matrix(cpus, gpus, optimal_func)
    return cpu_names, gpu_names, matrix


@st.cache_data(ttl=CACHE_TTL, hash_funcs={Session: lambda _: None})
def compute_heatmap_combined(db: Session):
    res_benefit = compute_heatmap_benefit(db)
    res_optimal = compute_heatmap_optimal(db)
    if res_benefit[0] is None or res_optimal[0] is None:
        return None, None, None
    cpu_names, gpu_names, benefit_mat = res_benefit
    _, _, optimal_mat = res_optimal
    if benefit_mat is None or optimal_mat is None:
        return None, None, None
    combined = [[(benefit_mat[i][j] * optimal_mat[i][j]) ** 0.5 for j in range(len(gpu_names))] for i in range(len(cpu_names))]
    return cpu_names, gpu_names, combined


@st.cache_data(ttl=CACHE_TTL, hash_funcs={Session: lambda _: None})
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


@st.cache_data(ttl=CACHE_TTL, hash_funcs={Session: lambda _: None})
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
            diff = abs((tdp / TDP_PHASE_RATIO - phase) ** 0.5)
            if diff == 0:
                val = 1
            else:
                val = (1.0 / diff) ** 0.5
            row.append(val)
        matrix.append(row)
    return cpu_names, mb_names, matrix


@st.cache_data(ttl=CACHE_TTL, hash_funcs={Session: lambda _: None})
def compute_heatmap_combined_cpu_mb(db: Session):
    res_benefit = compute_heatmap_cpu_mb_benefit(db)
    res_power = compute_heatmap_power(db)
    if res_benefit[0] is None or res_power[0] is None:
        return None, None, None
    cpu_names, mb_names, benefit_mat = res_benefit
    _, _, power_mat = res_power
    if benefit_mat is None or power_mat is None:
        return None, None, None
    combined = []
    for i in range(len(cpu_names)):
        row = []
        for j in range(len(mb_names)):
            b = benefit_mat[i][j]
            p = power_mat[i][j]
            if b is None or p is None:
                row.append(None)
            else:
                row.append((b * p) ** 0.5)
        combined.append(row)
    return cpu_names, mb_names, combined


# --- Рендеринг ---
def render(db: Session):
    st.markdown("<h2><i class='fas fa-square-poll-horizontal'></i> Тепловые карты</h2>", unsafe_allow_html=True)

    # Предварительная параллельная загрузка компонентов для ускорения первого запуска
    with ThreadPoolExecutor() as executor:
        future_cpu = executor.submit(get_cpu_components, db)
        future_gpu = executor.submit(get_gpu_components, db)
        future_mb = executor.submit(get_mb_components, db)
        # Ждём завершения, чтобы компоненты оказались в кэше (они не кэшируются,
        # но их загрузка запустится параллельно с вычислениями ниже)
        # Однако мы не будем явно ждать, так как вычисления всё равно будут использовать
        # get_cpu_components и т.д., которые могут уже быть в процессе загрузки.
        # Просто запускаем и не ждём, чтобы не блокировать отрисовку.
        # Но для уверенности можно сохранить объекты future, чтобы они не были собраны сборщиком мусора.
        pass  # Загрузка начнётся, но мы не блокируем

    tabs = st.tabs([
        "📊 Benefit CPU × GPU",
        "🎯 Оптимальность CPU и GPU",
        "🔗 Кривая подбора CPU и GPU",
        "📊 Benefit CPU × MB",
        "⚡ Power CPU и MB",
        "🔗 Кривая подбора CPU и MB"
    ])

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

    with tabs[3]:
        cpu_names, mb_names, raw_mat = compute_heatmap_cpu_mb_benefit(db)
        if cpu_names is None:
            st.warning("Недостаточно данных для Benefit (CPU × MB).")
        else:
            norm_mat = normalize_matrix(raw_mat)
            fig = px.imshow(norm_mat, x=mb_names, y=cpu_names,
                            labels=dict(x="Motherboard", y="CPU (модель)", color="Benefit (норм.)"),
                            title="Тепловая карта: Benefit_CPU × Benefit_MB (совместимые по сокету)",
                            color_continuous_scale="Plasma", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')

    with tabs[4]:
        cpu_names, mb_names, raw_mat = compute_heatmap_power(db)
        if cpu_names is None:
            st.warning("Недостаточно данных для Power (CPU × MB).")
        else:
            norm_mat = normalize_matrix(raw_mat)
            fig = px.imshow(norm_mat, x=mb_names, y=cpu_names,
                            labels=dict(x="Motherboard", y="CPU (модель)", color="Power (норм.)"),
                            title="Тепловая карта: √(1/|TDP/10.58 - Phase|)",
                            color_continuous_scale="Plasma", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')

    with tabs[5]:
        cpu_names, mb_names, raw_mat = compute_heatmap_combined_cpu_mb(db)
        if cpu_names is None:
            st.warning("Недостаточно данных для Кривой подбора (CPU × MB).")
        else:
            norm_mat = normalize_matrix(raw_mat)
            fig = px.imshow(norm_mat, x=mb_names, y=cpu_names,
                            labels=dict(x="Motherboard", y="CPU (модель)", color="Кривая (норм.)"),
                            title="Тепловая карта: √(Benefit_CPU_MB × Power_CPU_MB)",
                            color_continuous_scale="Plasma", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')