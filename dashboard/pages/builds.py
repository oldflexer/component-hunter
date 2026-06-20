import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor
from dnsight.core.database import SessionLocal
from dnsight.services.component_service import ComponentService
from dnsight.config.settings import GPU_TARGET_MULTIPLIER, TDP_PHASE_RATIO, INF_REPLACEMENT, CACHE_TTL
from dashboard.utils import get_last_price


@st.cache_data(ttl=CACHE_TTL)
def get_cpu_data():
    db = SessionLocal()
    try:
        service = ComponentService(db)
        cpus = service.get_cpu_components()
        return [{
            "name": cpu.name,
            "score": cpu.get_score(),
            "benefit": cpu.get_benefit(),
            "price": get_last_price(db, cpu._product.id) if cpu._product else 0,
            "socket": cpu.get_socket(),
            "tdp": cpu.get_tdp() if hasattr(cpu, "get_tdp") else 0,
        } for cpu in cpus if cpu.get_score() is not None]
    finally:
        db.close()


@st.cache_data(ttl=CACHE_TTL)
def get_gpu_data():
    db = SessionLocal()
    try:
        service = ComponentService(db)
        gpus = service.get_gpu_components()
        return [{
            "name": gpu.name,
            "score": gpu.get_score(),
            "benefit": gpu.get_benefit(),
            "price": get_last_price(db, gpu._product.id) if gpu._product else 0,
        } for gpu in gpus if gpu.get_score() is not None]
    finally:
        db.close()


@st.cache_data(ttl=CACHE_TTL)
def get_mb_data():
    db = SessionLocal()
    try:
        service = ComponentService(db)
        mbs = service.get_mb_components()
        return [{
            "name": mb.name,
            "benefit": mb.get_benefit(),
            "socket": mb.get_socket(),
            "price": get_last_price(db, mb.product_id) if mb.product_id else 0,
            "phase": mb.get_phase() if hasattr(mb, "get_phase") else 0,
        } for mb in mbs]
    finally:
        db.close()


def calculate_combined_gpu(cpu_benefit, gpu_benefit, cpu_delta, gpu_delta, cpu_score, gpu_score):
    if cpu_score is None or gpu_score is None:
        return 0.0
    target = cpu_score * GPU_TARGET_MULTIPLIER
    diff = abs(target - gpu_score)
    optimal = 1.0 / diff if diff != 0 else float('inf')
    combined = cpu_benefit * gpu_benefit * cpu_delta * gpu_delta * optimal
    return combined if combined != float('inf') else INF_REPLACEMENT


def calculate_combined_mb(cpu_benefit, mb_benefit, cpu_tdp, mb_phase):
    if cpu_tdp == 0 or mb_phase == 0:
        return 0.0
    diff = abs(cpu_tdp / TDP_PHASE_RATIO - mb_phase)
    power = (1.0 / diff) ** 0.5 if diff != 0 else INF_REPLACEMENT
    combined = (cpu_benefit * mb_benefit * power) ** 0.5
    return combined


def render_cpu_gpu_tab(cpu_data, gpu_data):
    st.header("Подбор CPU + GPU")
    st.markdown("Для каждого процессора показаны три лучшие видеокарты по комбинированной оценке.")
    if not cpu_data or not gpu_data:
        st.warning("Нет данных о CPU или GPU")
        return

    col1, col2 = st.columns(2)
    with col1:
        min_score = st.number_input("Минимальная сумма баллов CPU+GPU", min_value=0, value=0, step=1000)
    with col2:
        max_price = st.number_input("Максимальная стоимость (₽)", min_value=0, value=500_000, step=10000)

    all_pairs = []
    for cpu in cpu_data:
        if cpu["price"] == 0:
            continue
        cpu_score = cpu["score"]
        if cpu_score is None:
            continue
        cpu_benefit = cpu["benefit"]
        for gpu in gpu_data:
            if gpu["price"] == 0:
                continue
            gpu_score = gpu["score"]
            if gpu_score is None:
                continue
            total_score = cpu_score + gpu_score
            total_price = cpu["price"] + gpu["price"]
            if total_score < min_score or total_price > max_price:
                continue
            combined = calculate_combined_gpu(
                cpu_benefit, gpu["benefit"],
                1.0, 1.0,
                cpu_score, gpu_score
            )
            all_pairs.append({
                "CPU": cpu["name"],
                "GPU": gpu["name"],
                "Сумма баллов": total_score,
                "Стоимость (₽)": total_price,
                "Combined": combined,
            })

    if not all_pairs:
        st.warning("Нет пар, удовлетворяющих условиям.")
        return

    cpu_groups = {}
    for pair in all_pairs:
        cpu_name = pair["CPU"]
        cpu_groups.setdefault(cpu_name, []).append(pair)
    top_pairs = []
    for cpu_name, pairs in cpu_groups.items():
        sorted_pairs = sorted(pairs, key=lambda x: x["Combined"], reverse=True)
        top_pairs.extend(sorted_pairs[:3])

    df = pd.DataFrame(top_pairs)
    st.subheader(f"Топ-3 видеокарты для каждого процессора (всего {len(df)} записей)")
    st.dataframe(df[["CPU", "GPU", "Сумма баллов", "Стоимость (₽)", "Combined"]], width='stretch')


def render_cpu_mb_tab(cpu_data, mb_data):
    st.header("Подбор CPU + Motherboard")
    st.markdown("Для каждого процессора показаны три самые выгодные материнские платы.")
    if not cpu_data or not mb_data:
        st.warning("Нет данных о CPU или MB")
        return

    mb_by_socket = {}
    for mb in mb_data:
        socket = mb["socket"]
        if socket:
            mb_by_socket.setdefault(socket, []).append(mb)

    all_pairs = []
    for cpu in cpu_data:
        cpu_socket = cpu["socket"]
        if not cpu_socket or cpu_socket not in mb_by_socket:
            continue
        for mb in mb_by_socket[cpu_socket]:
            combined = calculate_combined_mb(
                cpu["benefit"],
                mb["benefit"],
                cpu["tdp"],
                mb["phase"]
            )
            all_pairs.append({
                "CPU": cpu["name"],
                "Motherboard": mb["name"],
                "Combined": combined,
            })

    if not all_pairs:
        st.warning("Нет совместимых пар.")
        return

    cpu_groups = {}
    for pair in all_pairs:
        cpu_name = pair["CPU"]
        cpu_groups.setdefault(cpu_name, []).append(pair)
    top_pairs = []
    for cpu_name, pairs in cpu_groups.items():
        sorted_pairs = sorted(pairs, key=lambda x: x["Combined"], reverse=True)
        top_pairs.extend(sorted_pairs[:3])

    df = pd.DataFrame(top_pairs)
    st.subheader(f"Топ-3 материнские платы для каждого процессора (всего {len(df)} записей)")
    st.dataframe(df[["CPU", "Motherboard", "Combined"]], width='stretch')


def render(db: Session):
    st.markdown("<h2><i class='fas fa-circle-check'></i> ПК-подбор</h2>", unsafe_allow_html=True)

    # Загружаем данные параллельно
    with ThreadPoolExecutor() as executor:
        future_cpu = executor.submit(get_cpu_data)
        future_gpu = executor.submit(get_gpu_data)
        future_mb = executor.submit(get_mb_data)
        cpu_data = future_cpu.result()
        gpu_data = future_gpu.result()
        mb_data = future_mb.result()

    tabs = st.tabs(["CPU+GPU", "CPU+MB"])
    with tabs[0]:
        render_cpu_gpu_tab(cpu_data, gpu_data)
    with tabs[1]:
        render_cpu_mb_tab(cpu_data, mb_data)