import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import time
from dnsight.core.database import init_db, get_db
from dnsight.parsers.dns import DNSParser
from dnsight.workers.saver import save_product_and_attributes
from dnsight.workers.update_passmark import update_passmark_scores
from dnsight.core.config import DNS_CATEGORIES
from dnsight.core.models import Product, Attribute, AttributeValue, PriceHistory, ModelScore, BenefitHistory, ProductType, Model
from dnsight.core.logging import get_logger
from sqlalchemy import func

st.set_page_config(page_title="DNSight Dashboard", layout="wide")
st.title("📊 DNSight")

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

def run_dns_parsing():
    dashboard_logger = get_logger("dashboard", "logs/dashboard.log", mode='w')
    parser = DNSParser(headless=False)
    try:
        for cat_key, type_name in CATEGORY_TO_TYPE.items():
            if cat_key not in DNS_CATEGORIES:
                dashboard_logger.warning(f"Категория {cat_key} отсутствует в конфиге, пропускаем")
                continue
            st.info(f"Парсинг DNS: {cat_key}...")
            dashboard_logger.info(f"Запуск парсинга категории {cat_key}")
            products = parser.parse_category(cat_key)
            st.write(f"Найдено {len(products)} товаров")
            for prod in products:
                specs = parser.parse_product_details(prod['url'])
                save_product_and_attributes(
                    db=db,
                    type_name=type_name,
                    product_name=prod['name'],
                    url=prod['url'],
                    price=prod['price'],
                    specs=specs
                )
                time.sleep(0.5)
    except Exception as e:
        dashboard_logger.exception("Ошибка в процессе парсинга DNS")
        st.error(f"Ошибка DNS: {e}")
    finally:
        parser.close()
    st.success("Парсинг DNS завершён!")
    dashboard_logger.info("Парсинг DNS завершён")

def run_passmark_update():
    try:
        update_passmark_scores(headless=False)
    except Exception as e:
        st.error(f"Ошибка PassMark: {e}")
        raise

def run_full_update():
    run_dns_parsing()
    run_passmark_update()

# --- Боковая панель ---
with st.sidebar:
    st.header("Управление")
    if st.button("🔄 Полный цикл", use_container_width=True):
        with st.spinner("Полный цикл..."):
            run_full_update()
        st.rerun()
    if st.button("🔸 Только DNS", use_container_width=True):
        with st.spinner("Парсинг DNS..."):
            run_dns_parsing()
        st.rerun()
    if st.button("🔥 Только PassMark", use_container_width=True):
        with st.spinner("Обновление баллов PassMark..."):
            run_passmark_update()
        st.rerun()
    st.markdown("---")
    
    # Выпадающий список с двумя опциями: "Таблицы" и "Аналитика"
    selected_page = st.selectbox("Выберите раздел", ["Таблицы", "Диагностика"])

# --- Основная область ---
if selected_page == "Таблицы":
    # Вкладки для каждой таблицы БД
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
        [
            "product_types",
            "models",
            "model_scores",
            "products",
            "attributes",
            "attribute_values",
            "price_history",
            "benefit_history"
        ]
    )

    with tab1:
        st.subheader("Типы продуктов (product_types)")
        data = db.query(ProductType).all()
        if data:
            df = pd.DataFrame([(r.id, r.name, r.description) for r in data],
                              columns=["id", "name", "description"])
            st.dataframe(df, width='stretch')
        else:
            st.info("Нет данных.")

    with tab2:
        st.subheader("Модели (models)")
        data = db.query(Model).all()
        if data:
            df = pd.DataFrame([(r.id, r.name, r.type_id) for r in data],
                              columns=["id", "name", "type_id"])
            st.dataframe(df, width='stretch')
        else:
            st.info("Нет данных. Запустите парсинг DNS.")

    with tab3:
        st.subheader("Скоры моделей (model_scores)")
        data = db.query(ModelScore).all()
        if data:
            df = pd.DataFrame([(r.id, r.model_id, r.score, r.source, r.updated_at) for r in data],
                              columns=["id", "model_id", "score", "source", "updated_at"])
            st.dataframe(df, width='stretch')
        else:
            st.info("Нет данных. Запустите обновление PassMark.")

    with tab4:
        st.subheader("Продукты (products)")
        data = db.query(Product).all()
        if data:
            df = pd.DataFrame([(r.id, r.type_id, r.model_id, r.name, r.url, r.created_at, r.updated_at) for r in data],
                              columns=["id", "type_id", "model_id", "name", "url", "created_at", "updated_at"])
            st.dataframe(df, width='stretch')
        else:
            st.info("Нет данных. Запустите парсинг DNS.")

    with tab5:
        st.subheader("Атрибуты (attributes)")
        data = db.query(Attribute).all()
        if data:
            df = pd.DataFrame([(r.id, r.name, r.type_id) for r in data],
                              columns=["id", "name", "type_id"])
            st.dataframe(df, width='stretch')
        else:
            st.info("Нет данных.")

    with tab6:
        st.subheader("Значения атрибутов (attribute_values)")
        data = db.query(AttributeValue).all()
        if data:
            df = pd.DataFrame([(r.id, r.product_id, r.attribute_id, r.raw_value, r.updated_at) for r in data],
                              columns=["id", "product_id", "attribute_id", "raw_value", "updated_at"])
            st.dataframe(df, width='stretch')
        else:
            st.info("Нет данных.")

    with tab7:
        st.subheader("История цен (price_history)")
        data = db.query(PriceHistory).all()
        if data:
            df = pd.DataFrame([(r.id, r.product_id, r.price, r.timestamp) for r in data],
                              columns=["id", "product_id", "price", "timestamp"])
            st.dataframe(df, width='stretch')
        else:
            st.info("Нет данных о ценах.")

    with tab8:
        st.subheader("История Benefit (benefit_history)")
        data = db.query(BenefitHistory).all()
        if data:
            df = pd.DataFrame([(r.id, r.product_id, r.benefit, r.timestamp) for r in data],
                              columns=["id", "product_id", "benefit", "timestamp"])
            st.dataframe(df, width='stretch')
        else:
            st.info("Нет данных о Benefit. Запустите парсинг DNS и PassMark.")

elif selected_page == "Аналитика":
    # Вкладки для CPU и GPU
    cpu_tab, gpu_tab = st.tabs(["CPU", "GPU"])
    
    # Функция для получения компонентов без характеристик
    def get_products_without_attributes(component_type_name: str) -> pd.DataFrame:
        # Находим тип продукта
        type_obj = db.query(ProductType).filter_by(name=component_type_name).first()
        if not type_obj:
            return pd.DataFrame()
        # Продукты этого типа, у которых нет записей в attribute_values
        products = db.query(Product).filter(
            Product.type_id == type_obj.id,
            ~Product.attribute_values.any()
        ).all()
        if products:
            return pd.DataFrame([(p.id, p.name, p.url) for p in products],
                                columns=["ID", "Name", "URL"])
        return pd.DataFrame()

    # Функция для получения компонентов без баллов PassMark
    def get_products_without_scores(component_type_name: str) -> pd.DataFrame:
        type_obj = db.query(ProductType).filter_by(name=component_type_name).first()
        if not type_obj:
            return pd.DataFrame()
        models_with_scores = db.query(ModelScore.model_id).distinct().subquery()
        products = db.query(Product).filter(
            Product.type_id == type_obj.id,
            Product.model_id.isnot(None),
            Product.model_id.notin_(models_with_scores)
        ).all()
        if products:
            return pd.DataFrame([(p.id, p.name, p.model.name if p.model else "Нет модели", p.url) for p in products],
                                columns=["ID", "Name", "Model Name", "URL"])
        return pd.DataFrame()

    with cpu_tab:
        st.subheader("CPU – без характеристик")
        df_no_attrs = get_products_without_attributes("CPU")
        if not df_no_attrs.empty:
            st.dataframe(df_no_attrs, width='stretch')
        else:
            st.info("Все CPU имеют характеристики.")
        
        st.subheader("CPU – без баллов PassMark")
        df_no_scores = get_products_without_scores("CPU")
        if not df_no_scores.empty:
            st.dataframe(df_no_scores, width='stretch')
        else:
            st.info("Все CPU имеют баллы PassMark.")

    with gpu_tab:
        st.subheader("GPU – без характеристик")
        df_no_attrs = get_products_without_attributes("GPU")
        if not df_no_attrs.empty:
            st.dataframe(df_no_attrs, width='stretch')
        else:
            st.info("Все GPU имеют характеристики.")
        
        st.subheader("GPU – без баллов PassMark")
        df_no_scores = get_products_without_scores("GPU")
        if not df_no_scores.empty:
            st.dataframe(df_no_scores, width='stretch')
        else:
            st.info("Все GPU имеют баллы PassMark.")