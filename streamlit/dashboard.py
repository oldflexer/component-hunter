import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import asyncio
from dnsight.core.database import init_db, get_db
from dnsight.parsers.dns import AsyncDNSParser
from dnsight.workers.saver import save_component_and_attributes
from dnsight.core.config import DNS_CATEGORIES
from dnsight.core.models import Component, Attribute, AttributeValue, PriceHistory, ModelScore, BenefitHistory, ComponentType, Model
from dnsight.core.logging import get_logger

st.set_page_config(page_title="DNSight Dashboard", layout="wide")
st.title("📊 DNSight - Аналитика комплектующих (async)")

init_db()
db = get_db()

CATEGORY_TO_TYPE = {
    "cpu": "CPU",
    "gpu": "GPU",
    "motherboard": "Motherboard",
    "ram_dimm": "RAM",
    "ram_sodimm": "RAM",
    "psu": "PSU",
    "case": "Case",
    "cooler": "Cooler",
    "lcs": "Cooler",
    "ssd": "Storage",
    "ssdm2": "Storage",
    "hdd35": "Storage",
    "hdd25": "Storage",
}

async def run_dns_parsing_async():
    dashboard_logger = get_logger("dashboard", "logs/dashboard.log", mode='w')
    parser = AsyncDNSParser()
    await parser.start_browser(headless=False)
    try:
        for cat_key, type_name in CATEGORY_TO_TYPE.items():
            # Проверяем, есть ли категория в DNS_CATEGORIES
            if cat_key not in DNS_CATEGORIES:
                dashboard_logger.warning(f"Категория {cat_key} отсутствует в конфиге, пропускаем")
                continue
            st.info(f"Парсинг DNS: {cat_key}...")
            dashboard_logger.info(f"Запуск категории {cat_key}")
            products = await parser.parse_category(cat_key)
            st.write(f"Найдено {len(products)} товаров")
            for prod in products:
                specs = await parser.parse_product_details(prod['url'])
                await save_component_and_attributes(
                    db=db,
                    type_name=type_name,
                    component_name=prod['name'],
                    dns_url=prod['url'],
                    price=prod['price'],
                    specs=specs
                )
                await asyncio.sleep(0.5)
    except Exception as e:
        dashboard_logger.exception("Ошибка DNS")
        st.error(f"Ошибка: {e}")
    finally:
        try:
            if parser.browser is not None:
                await parser.close_browser()
        except Exception as e:
            dashboard_logger.warning(f"Ошибка при закрытии браузера: {e}")
    st.success("Парсинг DNS завершён!")

async def run_full_update_async():
    await run_dns_parsing_async()
    # Пассмарк пока отключён, позже можно добавить:
    # await update_passmark_async()

# --- Боковая панель ---
with st.sidebar:
    st.header("Управление")
    if st.button("🚀 Полный цикл (DNS + PassMark)"):
        with st.spinner("Полный цикл..."):
            asyncio.run(run_full_update_async())
        st.rerun()
    if st.button("🌐 Только DNS"):
        with st.spinner("Парсинг DNS..."):
            asyncio.run(run_dns_parsing_async())
        st.rerun()
    st.markdown("---")
    st.info("Асинхронный парсинг на nodriver. PassMark временно отключён.")

# --- Вкладки ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["Компоненты", "Атрибуты", "Значения атрибутов", "История цен", "История скоров", "История Benefit"]
)

with tab1:
    st.subheader("Компоненты")
    comps = db.query(Component).all()
    df = pd.DataFrame([(c.id, c.type_id, c.name, c.dns_url) for c in comps],
                      columns=["ID", "Type ID", "Name", "DNS URL"])
    st.dataframe(df, width='stretch')

with tab2:
    st.subheader("Атрибуты")
    attrs = db.query(Attribute).all()
    df = pd.DataFrame([(a.id, a.name, a.type_id, a.aliases) for a in attrs],
                      columns=["ID", "Name", "Type ID", "Aliases"])
    st.dataframe(df, width='stretch')

with tab3:
    st.subheader("Значения атрибутов")
    vals = db.query(AttributeValue).all()
    df = pd.DataFrame([(v.id, v.component_id, v.attribute_id, v.value_raw) for v in vals],
                      columns=["ID", "Component ID", "Attribute ID", "Value"])
    st.dataframe(df, width='stretch')

with tab4:
    st.subheader("История цен")
    prices = db.query(PriceHistory).all()
    df = pd.DataFrame([(p.id, p.component_id, p.price, p.timestamp) for p in prices],
                      columns=["ID", "Component ID", "Price", "Timestamp"])
    st.dataframe(df, width='stretch')

with tab5:
    st.subheader("История скоров (PassMark)")
    query = db.query(
        Component.id.label("component_id"),
        Component.name.label("component_name"),
        Model.name.label("model_name"),
        ModelScore.score,
        ModelScore.source,
        ModelScore.updated_at.label("timestamp")
    ).join(Model, Component.model_id == Model.id, isouter=True)\
     .join(ModelScore, Model.id == ModelScore.model_id, isouter=True)\
     .order_by(ModelScore.updated_at.desc())
    results = query.all()
    if results:
        df = pd.DataFrame(results)
        st.dataframe(df, width='stretch')
    else:
        st.info("Нет данных о скорах. Запустите парсинг DNS, чтобы добавить модели.")

with tab6:
    st.subheader("История Benefit")
    benefits = db.query(BenefitHistory).all()
    df = pd.DataFrame([(b.id, b.component_id, b.benefit, b.timestamp) for b in benefits],
                      columns=["ID", "Component ID", "Benefit", "Timestamp"])
    st.dataframe(df, width='stretch')