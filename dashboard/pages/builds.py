import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from dnsight.services.component_service import ComponentService
from config.settings import GPU_TARGET_MULTIPLIER, TDP_PHASE_RATIO, INF_REPLACEMENT
from dashboard.utils import get_last_price


def calculate_combined_gpu(cpu_benefit, gpu_benefit, cpu_delta, gpu_delta, cpu_score, gpu_score):
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


def render_cpu_gpu_tab(db: Session):
    st.header("Подбор CPU + GPU")
    st.markdown("Для каждого процессора показаны три лучшие видеокарты по комбинированной оценке.")
    service = ComponentService(db)
    cpus = service.get_cpu_components()
    gpus = service.get_gpu_components()
    if not cpus or not gpus:
        st.warning("Нет данных о CPU или GPU")
        return

    col1, col2 = st.columns(2)
    with col1:
        min_score = st.number_input("Минимальная сумма баллов CPU+GPU", min_value=0, value=0, step=1000)
    with col2:
        max_price = st.number_input("Максимальная стоимость (₽)", min_value=0, value=500_000, step=10000)

    all_pairs = []
    for cpu in cpus:
        cpu_price = get_last_price(db, cpu._product.id) if cpu._product else 0
        if cpu_price == 0:
            continue
        for gpu in gpus:
            gpu_price = get_last_price(db, gpu._product.id) if gpu._product else 0
            if gpu_price == 0:
                continue
            total_score = cpu.get_score() + gpu.get_score()
            total_price = cpu_price + gpu_price
            if total_score < min_score or total_price > max_price:
                continue
            combined = calculate_combined_gpu(
                cpu.get_benefit(), gpu.get_benefit(),
                1.0, 1.0,  # delta пока не используется, можно добавить позже
                cpu.get_score(), gpu.get_score()
            )
            all_pairs.append({
                "CPU": cpu.name,
                "GPU": gpu.name,
                "Сумма баллов": total_score,
                "Стоимость (₽)": total_price,
                "Combined": combined,
            })

    if not all_pairs:
        st.warning("Нет пар, удовлетворяющих условиям.")
        return

    # Группировка по CPU, топ-3 по Combined
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


def render_cpu_mb_tab(db: Session):
    st.header("Подбор CPU + Motherboard")
    st.markdown("Для каждого процессора показаны три самые выгодные материнские платы.")
    service = ComponentService(db)
    cpus = service.get_cpu_components()
    mbs = service.get_mb_components()
    if not cpus or not mbs:
        st.warning("Нет данных о CPU или MB")
        return

    # Группировка MB по сокету
    mb_by_socket = {}
    for mb in mbs:
        socket = mb.get_socket()
        if socket:
            mb_by_socket.setdefault(socket, []).append(mb)

    all_pairs = []
    for cpu in cpus:
        cpu_socket = cpu.get_socket()
        if not cpu_socket or cpu_socket not in mb_by_socket:
            continue
        for mb in mb_by_socket[cpu_socket]:
            combined = calculate_combined_mb(
                cpu.get_benefit(),
                mb.get_benefit(),
                cpu.get_tdp() if hasattr(cpu, "get_tdp") else 0,
                mb.get_phase() if hasattr(mb, "get_phase") else 0
            )
            all_pairs.append({
                "CPU": cpu.name,
                "Motherboard": mb.name,
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
    tabs = st.tabs(["CPU+GPU", "CPU+MB"])
    with tabs[0]:
        render_cpu_gpu_tab(db)
    with tabs[1]:
        render_cpu_mb_tab(db)