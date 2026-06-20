import sys
from pathlib import Path
import time

from dnsight.core.logging import get_logger
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from dnsight.core.database import init_db, get_db
from dnsight.parsers.dns import DNSParser
from dnsight.workers.saver import save_product_and_attributes
from dnsight.workers.update_passmark import update_passmark_scores
from dnsight.config.settings import DNS_CATEGORIES
from dashboard.pages import summary, tables, diagnostics, forms, graphs, analytics, queries, selection, heatmaps, builds
from dnsight.config.settings import CATEGORY_MAPPING as CATEGORY_TO_TYPE
import base64
from pathlib import Path

def get_image_base64(path):
    with open(path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

logo_base64 = get_image_base64("static/logo.png")

st.set_page_config(page_title="Component Hunter", layout="wide", page_icon="static/favicon.ico")

st.markdown("""
<style>
    [data-testid="stSidebarHeader"] {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
    .stMainBlockContainer {
        padding-top: 0px !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
    [data-testid="stSidebarContent"] {
        padding-top: 10px !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css">
""", unsafe_allow_html=True)

init_db()
db = get_db()

# ------------------------------------------------------------------
# Функции для кнопок управления (можно оставить здесь или вынести)
# ------------------------------------------------------------------
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
                save_product_and_attributes(db, type_name, prod['name'], prod['url'], prod['price'], specs)
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

# ------------------------------------------------------------------
# Боковая панель
# ------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
        <img src="data:image/png;base64,{logo_base64}" width="100" style="vertical-align: middle;">
        <h1 style="margin: 0; vertical-align: middle; font-size: 2rem;">Component Hunter</h1>
    </div>
    """, unsafe_allow_html=True)

    st.header("Управление")
    if st.button("🔄 Полный цикл", width='stretch'):
        with st.spinner("Полный цикл..."):
            run_full_update()
        st.rerun()
    if st.button("🔸 Только DNS", width='stretch'):
        with st.spinner("Парсинг DNS..."):
            run_dns_parsing()
        st.rerun()
    if st.button("🔥 Только PassMark", width='stretch'):
        with st.spinner("Обновление баллов PassMark..."):
            run_passmark_update()
        st.rerun()
    st.markdown("---")

    selected_page = st.radio(
        "Выберите раздел",
        ["Сводка",
         "Таблицы",
         "Диагностика",
         "Формы",
         "Графики",
         "Аналитика",
         "Запросы",
         "Подбор компонентов",
         "Тепловые карты",
         "ПК-подбор"],
        index=0
    )

# ------------------------------------------------------------------
# Рендеринг выбранной страницы
# ------------------------------------------------------------------
if selected_page == "Сводка":
    summary.render(db)
elif selected_page == "Таблицы":
    tables.render(db)
elif selected_page == "Диагностика":
    diagnostics.render(db)
elif selected_page == "Формы":
    forms.render(db)
elif selected_page == "Графики":
    graphs.render(db)
elif selected_page == "Аналитика":
    analytics.render(db)
elif selected_page == "Запросы":
    queries.render(db)
elif selected_page == "Подбор компонентов":
    selection.render(db)
elif selected_page == "Тепловые карты":
    heatmaps.render(db)
elif selected_page == "ПК-подбор":
    builds.render(db)