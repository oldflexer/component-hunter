import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import time
from dnsight.core.database import init_db, get_db
from dnsight.parsers.dns import DNSParser
from dnsight.parsers.passmark import PassMarkParser
from dnsight.workers.saver import save_product_and_attributes, update_model_score
from dnsight.core.config import DNS_CATEGORIES
from dnsight.core.models import Product, Attribute, AttributeValue, PriceHistory, ModelScore, BenefitHistory, ProductType, Model
from dnsight.core.logging import get_logger

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

def run_dns_parsing():
    dashboard_logger = get_logger("dashboard", "logs/dashboard.log", mode='w')
    parser = DNSParser()
    try:
        for cat_key, type_name in CATEGORY_TO_TYPE.items():
            # Пропускаем, если категория не указана в конфиге
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

def update_passmark_scores():
    logger = get_logger("passmark_updater", "logs/passmark_updater.log", mode='a')
    parser = PassMarkParser(headless=True)
    try:
        cpu_type = db.query(ProductType).filter_by(name="CPU").first()
        gpu_type = db.query(ProductType).filter_by(name="GPU").first()
        type_ids = []
        if cpu_type:
            type_ids.append(cpu_type.id)
        if gpu_type:
            type_ids.append(gpu_type.id)
        if not type_ids:
            st.warning("Типы CPU или GPU не найдены в БД. Сначала запустите парсинг DNS.")
            return

        models = db.query(Model).filter(Model.type_id.in_(type_ids)).all()
        st.info(f"Найдено моделей для обновления: {len(models)}")
        progress_bar = st.progress(0)
        for idx, model in enumerate(models):
            last_score = db.query(ModelScore).filter_by(model_id=model.id).order_by(ModelScore.updated_at.desc()).first()
            if last_score and (pd.Timestamp.now() - pd.Timestamp(last_score.updated_at)).days < 7:
                continue
            product_type_name = db.query(ProductType).filter_by(id=model.type_id).first().name
            score = parser.get_score(model.name, product_type_name)
            if score is not None:
                update_model_score(db, model.id, score, source="passmark")
                logger.info(f"Обновлён скор для {model.name}: {score}")
            else:
                logger.warning(f"Не удалось получить скор для {model.name}")
            time.sleep(2)
            progress_bar.progress((idx + 1) / len(models))
        st.success("Обновление PassMark завершено!")
    except Exception as e:
        logger.exception("Ошибка при обновлении PassMark")
        st.error(f"Ошибка PassMark: {e}")
    finally:
        parser.close()

def run_full_update():
    run_dns_parsing()
    update_passmark_scores()

# --- Боковая панель ---
with st.sidebar:
    st.header("Управление")
    if st.button("🔄 Полный цикл (DNS + PassMark)"):
        with st.spinner("Полный цикл..."):
            run_full_update()
        st.rerun()
    if st.button("🌐 Только DNS"):
        with st.spinner("Парсинг DNS..."):
            run_dns_parsing()
        st.rerun()
    if st.button("⭐ Только PassMark"):
        with st.spinner("Обновление баллов PassMark..."):
            update_passmark_scores()
        st.rerun()
    st.markdown("---")
    st.info("Данные обновляются при каждом запуске. PassMark обновляет только модели CPU/GPU.")

# --- Вкладки для просмотра данных (адаптированы под новую схему) ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["Продукты", "Атрибуты", "Значения атрибутов", "История цен", "История скоров", "История Benefit"]
)

with tab1:
    st.subheader("Продукты")
    products = db.query(Product).all()
    df = pd.DataFrame([(p.id, p.type_id, p.name, p.url) for p in products],
                      columns=["ID", "Type ID", "Name", "URL"])
    st.dataframe(df, width='stretch')

with tab2:
    st.subheader("Атрибуты (характеристики)")
    attrs = db.query(Attribute).all()
    df = pd.DataFrame([(a.id, a.name, a.type_id) for a in attrs],
                      columns=["ID", "Name", "Type ID"])
    st.dataframe(df, width='stretch')

with tab3:
    st.subheader("Значения атрибутов")
    vals = db.query(AttributeValue).all()
    df = pd.DataFrame([(v.id, v.product_id, v.attribute_id, v.raw_value) for v in vals],
                      columns=["ID", "Product ID", "Attribute ID", "Value"])
    st.dataframe(df, width='stretch')

with tab4:
    st.subheader("История цен")
    prices = db.query(PriceHistory).all()
    df = pd.DataFrame([(p.id, p.product_id, p.price, p.timestamp) for p in prices],
                      columns=["ID", "Product ID", "Price", "Timestamp"])
    st.dataframe(df, width='stretch')

with tab5:
    st.subheader("История скоров (PassMark)")
    query = db.query(
        Product.id.label("product_id"),
        Product.name.label("product_name"),
        Model.name.label("model_name"),
        ModelScore.score,
        ModelScore.source,
        ModelScore.updated_at.label("timestamp")
    ).join(Model, Product.model_id == Model.id, isouter=True)\
     .join(ModelScore, Model.id == ModelScore.model_id, isouter=True)\
     .order_by(ModelScore.updated_at.desc())
    results = query.all()
    if results:
        df = pd.DataFrame(results)
        st.dataframe(df, width='stretch')
    else:
        st.info("Нет данных о скорах. Запустите парсинг, чтобы получить баллы PassMark.")

with tab6:
    st.subheader("История Benefit")
    benefits = db.query(BenefitHistory).all()
    df = pd.DataFrame([(b.id, b.product_id, b.benefit, b.timestamp) for b in benefits],
                      columns=["ID", "Product ID", "Benefit", "Timestamp"])
    st.dataframe(df, width='stretch')