import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import time
from dnsight.core.database import init_db, get_db
from dnsight.parsers.dns import DNSParser
from dnsight.workers.saver import save_component_and_attributes
from dnsight.core.config import DNS_CATEGORIES
from dnsight.core.models import Component, Attribute, AttributeValue, PriceHistory, ScoreHistory, BenefitHistory, ComponentType

st.set_page_config(page_title="DNSight Dashboard", layout="wide")
st.title("📊 DNSight - Аналитика комплектующих")

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

def run_parsing():
    # Если хотите использовать ваш локальный chromedriver:
    parser = DNSParser()
    # или для автоматической загрузки: parser = DNSParser()
    try:
        for cat_key, type_name in CATEGORY_TO_TYPE.items():
            st.info(f"Парсинг {cat_key}...")
            products = parser.parse_category(cat_key, max_pages=1, max_items=3)
            st.write(f"Найдено {len(products)} товаров")
            for prod in products:
                specs = parser.parse_product_details(prod['url'])
                save_component_and_attributes(
                    db=db,
                    type_name=type_name,
                    component_name=prod['name'],
                    dns_url=prod['url'],
                    price=prod['price'],
                    specs=specs
                )
                time.sleep(0.5)
    finally:
        parser.close()
    st.success("Парсинг завершён!")

with st.sidebar:
    st.header("Управление")
    if st.button("🚀 Запустить парсинг (3 товара на категорию)"):
        with st.spinner("Идёт парсинг..."):
            run_parsing()
        st.rerun()

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
    st.subheader("Атрибуты (характеристики)")
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
    scores = db.query(ScoreHistory).all()
    df = pd.DataFrame([(s.id, s.component_id, s.score, s.source, s.timestamp) for s in scores],
                      columns=["ID", "Component ID", "Score", "Source", "Timestamp"])
    st.dataframe(df, width='stretch')

with tab6:
    st.subheader("История Benefit")
    benefits = db.query(BenefitHistory).all()
    df = pd.DataFrame([(b.id, b.component_id, b.benefit, b.timestamp) for b in benefits],
                      columns=["ID", "Component ID", "Benefit", "Timestamp"])
    st.dataframe(df, width='stretch')

st.sidebar.markdown("---")
st.sidebar.info("Данные обновляются при каждом запуске парсинга. Таблицы истории пополняются новыми записями.")