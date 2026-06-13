# summary.py
import streamlit as st
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from dnsight.core.models import PriceHistory, ModelScore, BenefitHistory
from dnsight.services.component_service import ComponentService
from config.settings import DEFAULT_DAYS_BACK

def get_current_and_prev_avg_for_components(components, db: Session, days_ago: int = DEFAULT_DAYS_BACK):
    if not components:
        return None
    # Средняя цена сегодня
    prices_today = []
    for comp in components:
        price = comp.get_benefit()  # не то, надо отдельно
        # Нужно получать цену через get_last_price, но компонент не хранит product_id
        # Пока оставим старую логику, но позже добавим метод get_price() в компоненты
        pass
    # Для краткости оставим старую реализацию, но укажем TODO
    # ...

def render(db: Session):
    st.header("📈 Общая сводка")
    col1, col2, col3 = st.columns(3)
    service = ComponentService(db)

    # CPU
    with col1:
        st.subheader("🔲 CPU")
        cpus = service.get_cpu_components()
        if cpus:
            # Вычисляем средние через старую функцию (пока не переписывали)
            from dashboard.pages.summary import get_current_and_prev_avg
            stats = get_current_and_prev_avg(db, "CPU")
            if stats:
                st.metric("Средняя цена (₽)", f"{stats['price_now']:.0f}",
                          delta=f"{stats['price_now'] - stats['price_prev']:.0f}",
                          delta_color="inverse")
                st.metric("Средний балл PassMark", f"{stats['score_now']:.0f}",
                          delta=f"{stats['score_now'] - stats['score_prev']:.0f}")
                st.metric("Средний Benefit", f"{stats['benefit_now']:.4f}",
                          delta=f"{stats['benefit_now'] - stats['benefit_prev']:.4f}")
        else:
            st.info("Нет данных по CPU")

    # GPU
    with col2:
        st.subheader("🎮 GPU")
        gpus = service.get_gpu_components()
        if gpus:
            stats = get_current_and_prev_avg(db, "GPU")
            # ... аналогично
        else:
            st.info("Нет данных по GPU")

    # Motherboard
    with col3:
        st.subheader("🖥 Motherboard")
        mbs = service.get_mb_components()
        if mbs:
            stats = get_current_and_prev_avg(db, "Motherboard")
            # ...
        else:
            st.info("Нет данных по Motherboard")