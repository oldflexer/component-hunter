import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from dnsight.services.component_service import ComponentService
from dnsight.config.settings import GPU_TARGET_MULTIPLIER
from dashboard.utils import get_last_price, get_last_benefit, get_last_score


def render(db: Session):
    tabs = st.tabs(["Подбор GPU под CPU", "Подбор CPU под GPU", "Подбор CPU под MB", "Подбор MB под CPU"])
    service = ComponentService(db)

    # ---- Подбор GPU под CPU ----
    with tabs[0]:
        st.subheader("Выберите CPU, чтобы увидеть рекомендуемые GPU")
        cpus = service.get_cpu_components()
        if not cpus:
            st.info("Нет CPU с баллами PassMark")
        else:
            cpu_names = [cpu.name for cpu in cpus]
            selected_cpu_name = st.selectbox("Выберите CPU", cpu_names, key="cpu_select")
            selected_cpu = next(cpu for cpu in cpus if cpu.name == selected_cpu_name)
            cpu_score = selected_cpu.get_score()
            if cpu_score is None:
                st.error("У выбранного CPU нет балла PassMark")
            else:
                target_gpu_score = cpu_score * GPU_TARGET_MULTIPLIER
                st.info(f"Целевой балл GPU: {target_gpu_score:.0f}")

                gpus = service.get_gpu_components()
                gpu_data = []
                for gpu in gpus:
                    score = gpu.get_score()
                    if score is None:
                        continue
                    price = get_last_price(db, gpu._product.id) if gpu._product else 0
                    benefit = gpu.get_benefit()
                    deviation = abs(score - target_gpu_score) / target_gpu_score if target_gpu_score > 0 else 999
                    gpu_data.append({
                        "Model Name": gpu.name,
                        "Score": score,
                        "Price (RUB)": price,
                        "Benefit": benefit,
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
        gpus = service.get_gpu_components()
        if not gpus:
            st.info("Нет GPU с баллами PassMark")
        else:
            gpu_names = [gpu.name for gpu in gpus]
            selected_gpu_name = st.selectbox("Выберите GPU", gpu_names, key="gpu_select")
            selected_gpu = next(gpu for gpu in gpus if gpu.name == selected_gpu_name)
            gpu_score = selected_gpu.get_score()
            if gpu_score is None:
                st.error("У выбранного GPU нет балла PassMark")
            else:
                target_cpu_score = gpu_score / GPU_TARGET_MULTIPLIER
                st.info(f"Целевой балл CPU: {target_cpu_score:.0f}")

                cpus = service.get_cpu_components()
                cpu_data = []
                for cpu in cpus:
                    score = cpu.get_score()
                    if score is None:
                        continue
                    price = get_last_price(db, cpu._product.id) if cpu._product else 0
                    benefit = cpu.get_benefit()
                    deviation = abs(score - target_cpu_score) / target_cpu_score if target_cpu_score > 0 else 999
                    cpu_data.append({
                        "Model Name": cpu.name,
                        "Score": score,
                        "Price (RUB)": price,
                        "Benefit": benefit,
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
        mbs = service.get_mb_components()
        if not mbs:
            st.info("Нет MB с указанным сокетом")
        else:
            mb_names = [mb.name for mb in mbs]
            selected_mb_name = st.selectbox("Выберите материнскую плату", mb_names, key="mb_select")
            selected_mb = next(mb for mb in mbs if mb.name == selected_mb_name)
            socket = selected_mb.get_socket()
            st.info(f"Сокет: {socket}")

            cpus = service.get_cpu_components()
            compatible_cpu = []
            for cpu in cpus:
                if cpu.get_socket() == socket:
                    compatible_cpu.append({
                        "Model Name": cpu.name,
                        "Score": cpu.get_score() or 0,
                        "Price (RUB)": get_last_price(db, cpu._product.id) if cpu._product else 0,
                        "Benefit": cpu.get_benefit(),
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
        cpus = service.get_cpu_components()
        if not cpus:
            st.info("Нет CPU с сокетом")
        else:
            cpu_names = [cpu.name for cpu in cpus]
            selected_cpu_name = st.selectbox("Выберите CPU", cpu_names, key="cpu_select_mb")
            selected_cpu = next(cpu for cpu in cpus if cpu.name == selected_cpu_name)
            socket = selected_cpu.get_socket()
            st.info(f"Сокет: {socket}")

            mbs = service.get_mb_components()
            compatible_mb = []
            for mb in mbs:
                if mb.get_socket() == socket:
                    compatible_mb.append({
                        "Model Name": mb.name,
                        "Price (RUB)": get_last_price(db, mb.product_id) if mb.product_id else 0,
                        "Benefit": mb.get_benefit(),
                    })
            if compatible_mb:
                df = pd.DataFrame(compatible_mb)
                max_benefit = df['Benefit'].max()
                df['Benefit %'] = (df['Benefit'] / max_benefit * 100).round(1) if max_benefit > 0 else 0
                df = df.sort_values(by="Benefit", ascending=False)
                st.dataframe(df[["Model Name", "Price (RUB)", "Benefit", "Benefit %"]], width='stretch')
            else:
                st.info("Нет совместимых MB")