import sys
from pathlib import Path
import time
import base64
from datetime import timedelta

from dnsight.core.logging import get_logger
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from dnsight.core.database import init_db, get_db
from dnsight.parsers.dns import DNSParser
from dnsight.workers.saver import save_product_and_attributes
from dnsight.workers.update_passmark import update_passmark_scores
from dnsight.workers.recalc import recalculate_scores
from dnsight.config.settings import DNS_CATEGORIES
from dashboard.pages import summary, tables, diagnostics, forms, graphs, analytics, queries, selection, heatmaps, builds
from dnsight.config.settings import CATEGORY_MAPPING as CATEGORY_TO_TYPE

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
            
    [data-testid="stSidebarUserContent"] {
        padding-top: 10px !important;
    }
            
    [class*="en7m6i63"] {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css">
""", unsafe_allow_html=True)

init_db()
db = get_db()

# ------------------------------------------------------------------
# Функции с поддержкой прогресс-бара
# ------------------------------------------------------------------

def run_dns_parsing(progress_bar=None, text_callback=None) -> set:
    """Парсинг DNS с обновлением прогресса."""
    parser = None
    dashboard_logger = get_logger("dashboard", "logs/dashboard.log", mode='w')
    processed_types = set()

    categories_to_parse = [k for k in CATEGORY_TO_TYPE if k in DNS_CATEGORIES]
    total_categories = len(categories_to_parse)

    if text_callback:
        text_callback(f"Всего категорий: {total_categories}")

    start_time = time.time()
    total_products_processed = 0

    try:
        parser = DNSParser(headless=False)
        for idx_cat, cat_key in enumerate(categories_to_parse, 1):
            type_name = CATEGORY_TO_TYPE[cat_key]
            if text_callback:
                text_callback(f"DNS: {cat_key} ({idx_cat}/{total_categories})")

            try:
                products = parser.parse_category(cat_key)
            except Exception as e:
                dashboard_logger.error(f"Ошибка парсинга {cat_key}: {e}")
                if text_callback:
                    text_callback(f"❌ Ошибка: {e}")
                continue

            processed_types.add(type_name)
            total_products = len(products)
            if text_callback:
                text_callback(f"Найдено {total_products} товаров в {cat_key}")

            for idx_prod, prod in enumerate(products, 1):
                try:
                    specs = parser.parse_product_details(prod['url'])
                    save_product_and_attributes(db, type_name, prod['name'], prod['url'], prod['price'], specs)
                except Exception as e:
                    dashboard_logger.error(f"Ошибка обработки {prod['name']}: {e}")
                    if text_callback:
                        text_callback(f"⚠️ Ошибка: {e}")
                    continue

                total_products_processed += 1
                elapsed_total = time.time() - start_time
                avg_time_per_item = elapsed_total / total_products_processed if total_products_processed > 0 else 0
                remaining_in_category = total_products - idx_prod
                eta_seconds = avg_time_per_item * remaining_in_category
                eta_str = str(timedelta(seconds=int(eta_seconds))) if eta_seconds > 0 else "< 1 сек"

                category_progress = idx_prod / total_products
                overall_progress = (idx_cat - 1 + category_progress) / total_categories
                overall_progress = min(overall_progress, 1.0)

                if progress_bar:
                    progress_bar.progress(overall_progress)
                if text_callback:
                    text_callback(f"Обработано {total_products_processed} товаров, осталось ~{remaining_in_category} в категории, ETA: {eta_str}")

                time.sleep(0.1)

    except Exception as e:
        dashboard_logger.exception("Критическая ошибка в DNS")
        if text_callback:
            text_callback(f"❌ Критическая ошибка: {e}")
        raise
    finally:
        if parser:
            parser.close()
            dashboard_logger.info("Драйвер закрыт")
        else:
            dashboard_logger.warning("Парсер не был создан, закрытие пропущено")

    if text_callback:
        text_callback("✅ DNS завершён")
    dashboard_logger.info("Парсинг DNS завершён")
    return processed_types

def run_passmark_update(update_cpu=True, update_gpu=True, progress_bar=None, text_callback=None):
    """Обновление PassMark с прогрессом."""
    if not update_cpu and not update_gpu:
        if text_callback:
            text_callback("PassMark пропущен (нет CPU/GPU)")
        return
    if text_callback:
        text_callback("Обновление PassMark...")
    try:
        # Передаём callback для обновления текста (без прогресс-бара, т.к. внутри update_passmark_scores нет прогресса)
        # Можно передать progress_bar, но он не используется внутри update_passmark_scores, если не доработать.
        # Пока просто вызываем как есть.
        update_passmark_scores(headless=False, update_cpu=update_cpu, update_gpu=update_gpu)
        if text_callback:
            text_callback("✅ PassMark обновлён")
    except Exception as e:
        if text_callback:
            text_callback(f"❌ Ошибка PassMark: {e}")
        raise

def run_recalc_scores(progress_bar=None, text_callback=None):
    """Пересчёт баллов с прогрессом."""
    if text_callback:
        text_callback("Пересчёт баллов...")
    try:
        recalculate_scores(progress_bar=progress_bar, text_callback=text_callback)
        if text_callback:
            text_callback("✅ Пересчёт завершён")
    except Exception as e:
        if text_callback:
            text_callback(f"❌ Ошибка пересчёта: {e}")
        raise

def run_full_update():
    """Полный цикл с единым прогресс-баром."""
    progress_bar = st.progress(0)
    status_text = st.empty()
    status_text.text("Начинаем полный цикл...")

    try:
        # Этап 1: DNS
        status_text.text("Запуск DNS...")
        processed = run_dns_parsing(progress_bar=progress_bar, text_callback=status_text.text)

        # Этап 2: PassMark (если есть CPU/GPU)
        update_cpu = "CPU" in processed
        update_gpu = "GPU" in processed
        if update_cpu or update_gpu:
            status_text.text("Запуск PassMark...")
            # Обнуляем прогресс? Лучше оставить общий прогресс, но мы не можем его сбросить.
            # Можно использовать отдельный прогресс для PassMark, но это нарушит единую шкалу.
            # Поэтому просто вызываем без изменения прогресс-бара.
            run_passmark_update(update_cpu=update_cpu, update_gpu=update_gpu, text_callback=status_text.text)
        else:
            status_text.text("PassMark пропущен (нет CPU/GPU)")

        # Этап 3: Пересчёт
        status_text.text("Запуск пересчёта баллов...")
        run_recalc_scores(progress_bar=progress_bar, text_callback=status_text.text)

        progress_bar.progress(1.0)
        status_text.text("✅ Полный цикл завершён!")
        st.success("✅ Полный цикл успешно выполнен!")
    except Exception as e:
        status_text.text(f"❌ Ошибка: {e}")
        st.error(f"❌ Ошибка: {e}")
    finally:
        st.rerun()

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
        run_full_update()

    if st.button("🔸 Только DNS", width='stretch'):
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text("Начинаем парсинг DNS...")
        try:
            run_dns_parsing(progress_bar=progress_bar, text_callback=status_text.text)
            progress_bar.progress(1.0)
            status_text.text("✅ DNS завершён")
            st.success("✅ Парсинг DNS завершён!")
        except Exception as e:
            status_text.text(f"❌ Ошибка: {e}")
            st.error(f"❌ Ошибка: {e}")
        st.rerun()

    if st.button("🔥 Только PassMark", width='stretch'):
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text("Начинаем обновление PassMark...")
        try:
            # PassMark не имеет внутреннего прогресса, поэтому просто показываем индикатор
            run_passmark_update(update_cpu=True, update_gpu=True, text_callback=status_text.text)
            progress_bar.progress(1.0)
            status_text.text("✅ PassMark обновлён")
            st.success("✅ PassMark обновлён!")
        except Exception as e:
            status_text.text(f"❌ Ошибка: {e}")
            st.error(f"❌ Ошибка: {e}")
        st.rerun()

    if st.button("🧮 Расчёт баллов", width='stretch'):
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text("Начинаем пересчёт...")
        try:
            recalculate_scores(progress_bar=progress_bar, text_callback=status_text.text)
            progress_bar.progress(1.0)
            status_text.text("✅ Пересчёт завершён!")
            st.success("✅ Пересчёт баллов завершён!")
        except Exception as e:
            status_text.text(f"❌ Ошибка: {e}")
            st.error(f"❌ Ошибка: {e}")
        st.rerun()

    st.markdown("---")

    selected_page = st.radio(
        "Выберите раздел",
        ["Сводка", "Таблицы", "Диагностика", "Формы", "Графики",
         "Аналитика", "Запросы", "Подбор компонентов", "Тепловые карты", "ПК-подбор"],
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