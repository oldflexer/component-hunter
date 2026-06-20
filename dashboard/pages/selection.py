import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor
from dnsight.core.database import SessionLocal
from dnsight.services.component_service import ComponentService
from dnsight.config.settings import GPU_TARGET_MULTIPLIER, CACHE_TTL
from dashboard.utils import get_last_price


@st.cache_data(ttl=CACHE_TTL)
def get_cpu_list():
    db = SessionLocal()
    try:
        service = ComponentService(db)
        cpus = service.get_cpu_components()
        return [(cpu.name, cpu.get_score(), cpu.get_socket(), cpu.get_benefit(), cpu._product.id if cpu._product else None) for cpu in cpus if cpu.get_score() is not None]
    finally:
        db.close()


@st.cache_data(ttl=CACHE_TTL)
def get_gpu_list():
    db = SessionLocal()
    try:
        service = ComponentService(db)
        gpus = service.get_gpu_components()
        return [(gpu.name, gpu.get_score(), gpu.get_benefit(), gpu._product.id if gpu._product else None) for gpu in gpus if gpu.get_score() is not None]
    finally:
        db.close()


@st.cache_data(ttl=CACHE_TTL)
def get_mb_list():
    db = SessionLocal()
    try:
        service = ComponentService(db)
        mbs = service.get_mb_components()
        return [(mb.name, mb.get_socket(), mb.get_benefit(), mb.product_id) for mb in mbs]
    finally:
        db.close()


def render(db: Session):
    st.markdown("<h2><i class='fas fa-layer-group'></i> Подбор компонентов</h2>", unsafe_allow_html=True)

    # Загружаем все списки параллельно
    with ThreadPoolExecutor() as executor:
        future_cpu = executor.submit(get_cpu_list)
        future_gpu = executor.submit(get_gpu_list)
        future_mb = executor.submit(get_mb_list)
        cpus = future_cpu.result()
        gpus = future_gpu.result()
        mbs = future_mb.result()

    tabs = st.tabs(["Подбор GPU под CPU", "Подбор CPU под GPU", "Подбор CPU под MB", "Подбор MB под CPU"])

    # ---- Подбор GPU под CPU ----
    with tabs[0]:
        st.subheader("Выберите CPU, чтобы увидеть рекомендуемые GPU")
        if not cpus:
            st.info("Нет CPU с баллами PassMark")
        else:
            cpu_names = [c[0] for c in cpus]
            selected_cpu_name = st.selectbox("Выберите CPU", cpu_names, key="cpu_select")
            selected_cpu = next(c for c in cpus if c[0] == selected_cpu_name)
            cpu_score = selected_cpu[1]
            if cpu_score is None:
                st.error("У выбранного CPU нет балла PassMark")
            else:
                target_gpu_score = cpu_score * GPU_TARGET_MULTIPLIER
                st.info(f"Целевой балл GPU: {target_gpu_score:.0f}")

                gpu_data = []
                for gpu_name, gpu_score, gpu_benefit, gpu_product_id in gpus:
                    if gpu_score is None:
                        continue
                    price = get_last_price(db, gpu_product_id) if gpu_product_id else 0
                    deviation = abs(gpu_score - target_gpu_score) / target_gpu_score if target_gpu_score > 0 else 999
                    gpu_data.append({
                        "Model Name": gpu_name,
                        "Score": gpu_score,
                        "Price (RUB)": price,
                        "Benefit": gpu_benefit,
                        "Deviation": deviation,
                    })
                df = pd.DataFrame(gpu_data)
                if not df.empty:
                    max_benefit = df['Benefit'].max()
                    df['Benefit %'] = (df['Benefit'] / max_benefit * 100).round(1) if max_benefit > 0 else 0
                    df = df.sort_values(by="Deviation")
                    df["Match"] = df["Deviation"].apply(
                        lambda x: "⭐ Оптимально" if x < 0.2 else "👍 Хорошо" if x < 0.4 else "⚠️ Слабоват" if x > 0.6 else "👌 Приемлемо"
                    )
                    st.dataframe(df[["Model Name", "Score", "Price (RUB)", "Benefit", "Benefit %", "Match"]], width='stretch')

    # ---- Подбор CPU под GPU ----
    with tabs[1]:
        st.subheader("Выберите GPU, чтобы увидеть рекомендуемые CPU")
        if not gpus:
            st.info("Нет GPU с баллами PassMark")
        else:
            gpu_names = [g[0] for g in gpus]
            selected_gpu_name = st.selectbox("Выберите GPU", gpu_names, key="gpu_select")
            selected_gpu = next(g for g in gpus if g[0] == selected_gpu_name)
            gpu_score = selected_gpu[1]
            if gpu_score is None:
                st.error("У выбранного GPU нет балла PassMark")
            else:
                target_cpu_score = gpu_score / GPU_TARGET_MULTIPLIER
                st.info(f"Целевой балл CPU: {target_cpu_score:.0f}")

                cpu_data = []
                for cpu_name, cpu_score, cpu_socket, cpu_benefit, cpu_product_id in cpus:
                    if cpu_score is None:
                        continue
                    price = get_last_price(db, cpu_product_id) if cpu_product_id else 0
                    deviation = abs(cpu_score - target_cpu_score) / target_cpu_score if target_cpu_score > 0 else 999
                    cpu_data.append({
                        "Model Name": cpu_name,
                        "Score": cpu_score,
                        "Price (RUB)": price,
                        "Benefit": cpu_benefit,
                        "Deviation": deviation,
                    })
                df = pd.DataFrame(cpu_data)
                if not df.empty:
                    max_benefit = df['Benefit'].max()
                    df['Benefit %'] = (df['Benefit'] / max_benefit * 100).round(1) if max_benefit > 0 else 0
                    df = df.sort_values(by="Deviation")
                    df["Match"] = df["Deviation"].apply(
                        lambda x: "⭐ Оптимально" if x < 0.2 else "👍 Хорошо" if x < 0.4 else "⚠️ Слабоват" if x > 0.6 else "👌 Приемлемо"
                    )
                    st.dataframe(df[["Model Name", "Score", "Price (RUB)", "Benefit", "Benefit %", "Match"]], width='stretch')

    # ---- Подбор CPU под MB ----
    with tabs[2]:
        st.subheader("Выберите материнскую плату, чтобы увидеть совместимые CPU")
        if not mbs:
            st.info("Нет MB с указанным сокетом")
        else:
            mb_names = [m[0] for m in mbs]
            selected_mb_name = st.selectbox("Выберите материнскую плату", mb_names, key="mb_select")
            selected_mb = next(m for m in mbs if m[0] == selected_mb_name)
            socket = selected_mb[1]
            st.info(f"Сокет: {socket}")

            compatible_cpu = []
            for cpu_name, cpu_score, cpu_socket, cpu_benefit, cpu_product_id in cpus:
                if cpu_score is None:
                    continue
                if cpu_socket == socket:
                    price = get_last_price(db, cpu_product_id) if cpu_product_id else 0
                    compatible_cpu.append({
                        "Model Name": cpu_name,
                        "Score": cpu_score or 0,
                        "Price (RUB)": price,
                        "Benefit": cpu_benefit,
                    })
            if compatible_cpu:
                df = pd.DataFrame(compatible_cpu)
                max_benefit = df['Benefit'].max()
                df['Benefit %'] = (df['Benefit'] / max_benefit * 100).round(1) if max_benefit > 0 else 0
                df = df.sort_values(by="Benefit", ascending=False)
                st.dataframe(df[["Model Name", "Score", "Price (RUB)", "Benefit", "Benefit %"]], width='stretch')
            else:
                st.info("Нет совместимых CPU")

    # ---- Подбор MB под CPU ----
    with tabs[3]:
        st.subheader("Выберите процессор, чтобы увидеть совместимые материнские платы")
        if not cpus:
            st.info("Нет CPU с сокетом")
        else:
            cpu_names = [c[0] for c in cpus]
            selected_cpu_name = st.selectbox("Выберите CPU", cpu_names, key="cpu_select_mb")
            selected_cpu = next(c for c in cpus if c[0] == selected_cpu_name)
            socket = selected_cpu[2]
            st.info(f"Сокет: {socket}")

            compatible_mb = []
            for mb_name, mb_socket, mb_benefit, mb_product_id in mbs:
                if mb_socket == socket:
                    price = get_last_price(db, mb_product_id) if mb_product_id else 0
                    compatible_mb.append({
                        "Model Name": mb_name,
                        "Price (RUB)": price,
                        "Benefit": mb_benefit,
                    })
            if compatible_mb:
                df = pd.DataFrame(compatible_mb)
                max_benefit = df['Benefit'].max()
                df['Benefit %'] = (df['Benefit'] / max_benefit * 100).round(1) if max_benefit > 0 else 0
                df = df.sort_values(by="Benefit", ascending=False)
                st.dataframe(df[["Model Name", "Price (RUB)", "Benefit", "Benefit %"]], width='stretch')
            else:
                st.info("Нет совместимых MB")