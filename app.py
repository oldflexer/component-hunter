import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import time
import plotly.express as px
from datetime import datetime, timedelta
from sqlalchemy import func, and_, select, text
from typing import Optional

from dnsight.core.database import init_db, get_db
from dnsight.parsers.dns import DNSParser
from dnsight.workers.saver import save_product_and_attributes
from dnsight.workers.update_passmark import update_passmark_scores
from dnsight.core.config import DNS_CATEGORIES
from dnsight.core.models import (
    Product, Attribute, AttributeValue, PriceHistory,
    ModelScore, BenefitHistory, ProductType, Model
)
from dnsight.core.logging import get_logger

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
    
    selected_page = st.selectbox(
        "Выберите раздел",
        ["Таблицы", "Диагностика", "Графики", "Аналитика", "Подбор CPU/GPU", "Тепловые карты"]
    )

# --- Общие вспомогательные функции ---
def get_last_price(product_id: int):
    """Возвращает последнюю цену продукта."""
    ph = db.query(PriceHistory).filter_by(product_id=product_id).order_by(PriceHistory.timestamp.desc()).first()
    return ph.price if ph else None

def get_last_score(model_id: int):
    """Возвращает последний скор модели."""
    ms = db.query(ModelScore).filter_by(model_id=model_id).order_by(ModelScore.updated_at.desc()).first()
    return ms.score if ms else None

def get_last_benefit(product_id: int):
    """Возвращает последний Benefit продукта."""
    bh = db.query(BenefitHistory).filter_by(product_id=product_id).order_by(BenefitHistory.timestamp.desc()).first()
    return bh.benefit if bh else None

# ===========================
# 1. Таблицы с data_editor (удаление через чекбоксы в таблице)
# ===========================
if selected_page == "Таблицы":
    
    def render_table_with_data_editor(table_name: str, query, id_column: str, display_columns: list, column_names: list = None):
        """Отображает таблицу с колонкой чекбоксов (первая колонка, без заголовка) для удаления."""
        data = query.all()
        if not data:
            st.info(f"Нет данных в таблице {table_name}.")
            return

        # Создаём список словарей для DataFrame
        rows = []
        for row in data:
            row_dict = {}
            for col in display_columns:
                if isinstance(col, str):
                    val = getattr(row, col)
                else:
                    val = col
                row_dict[col if isinstance(col, str) else str(col)] = val
            rows.append(row_dict)

        df = pd.DataFrame(rows)
        if column_names:
            df.columns = column_names

        # Добавляем колонку для удаления (без названия)
        delete_col = "🗑️ Удалить?"
        df.insert(0, delete_col, False)   # вставляем первой

        # Настройка ширины колонок: для удаления делаем узкую
        column_config = {
            delete_col: st.column_config.CheckboxColumn(
                label="",   # пустой заголовок
                width=30,
                default=False
            ),
        }
        # Остальные колонки можно оставить с автошириной

        # Отображаем data_editor
        edited_df = st.data_editor(
            df,
            column_config=column_config,
            width='stretch',
            hide_index=True,
            key=f"data_editor_{table_name}"
        )

        if st.button(f"🗑️ Удалить отмеченные", key=f"del_selected_{table_name}"):
            to_delete_mask = edited_df[delete_col] == True
            if to_delete_mask.any():
                id_col_name = df.columns[1]
                ids_to_delete = edited_df.loc[to_delete_mask, id_col_name].tolist()
                confirm = st.checkbox(str(f"Подтвердить удаление {len(ids_to_delete)} записей?"), key=f"confirm_{table_name}")
                if confirm:
                    try:
                        model_class = query.column_descriptions[0]['type']
                        # Удаляем через ORM с синхронизацией 'fetch'
                        deleted = query.filter(getattr(model_class, id_column).in_(ids_to_delete)).delete(synchronize_session='fetch')
                        db.commit()
                        st.success(f"Удалено {deleted} записей.")
                        st.rerun()
                    except Exception as e:
                        db.rollback()
                        st.error(f"Ошибка удаления: {e}")
            else:
                st.info("Нет выбранных записей.")

    # Создаём вкладки для каждой таблицы
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
        ["product_types", "models", "model_scores", "products",
         "attributes", "attribute_values", "price_history", "benefit_history"]
    )
    
    with tab1:
        render_table_with_data_editor(
            "product_types",
            db.query(ProductType),
            "id",
            ["id", "name", "description"],
            ["id", "name", "description"]
        )
    
    with tab2:
        render_table_with_data_editor(
            "models",
            db.query(Model),
            "id",
            ["id", "name", "type_id"],
            ["id", "name", "type_id"]
        )
    
    with tab3:
        render_table_with_data_editor(
            "model_scores",
            db.query(ModelScore),
            "id",
            ["id", "model_id", "score", "source", "updated_at"],
            ["id", "model_id", "score", "source", "updated_at"]
        )
    
    with tab4:
        render_table_with_data_editor(
            "products",
            db.query(Product),
            "id",
            ["id", "type_id", "model_id", "name", "url", "created_at", "updated_at"],
            ["id", "type_id", "model_id", "name", "url", "created_at", "updated_at"]
        )
    
    with tab5:
        render_table_with_data_editor(
            "attributes",
            db.query(Attribute),
            "id",
            ["id", "name", "type_id"],
            ["id", "name", "type_id"]
        )
    
    with tab6:
        render_table_with_data_editor(
            "attribute_values",
            db.query(AttributeValue),
            "id",
            ["id", "product_id", "attribute_id", "raw_value", "updated_at"],
            ["id", "product_id", "attribute_id", "raw_value", "updated_at"]
        )
    
    with tab7:
        render_table_with_data_editor(
            "price_history",
            db.query(PriceHistory),
            "id",
            ["id", "product_id", "price", "timestamp"],
            ["id", "product_id", "price", "timestamp"]
        )
    
    with tab8:
        render_table_with_data_editor(
            "benefit_history",
            db.query(BenefitHistory),
            "id",
            ["id", "product_id", "benefit", "timestamp"],
            ["id", "product_id", "benefit", "timestamp"]
        )

# ===========================
# 2. Диагностика с возможностью удаления выбранных проблемных товаров
# ===========================
elif selected_page == "Диагностика":
    cpu_tab, gpu_tab = st.tabs(["CPU", "GPU"])
    
    def render_problem_table(title: str, df: pd.DataFrame, product_ids: list, key_suffix: str):
        """Отображает таблицу с чекбоксами для удаления выбранных товаров."""
        if df.empty:
            st.success(f"✅ {title} – проблем нет!")
            return
        
        st.subheader(title)
        # Добавляем колонку чекбоксов
        df_with_check = df.copy()
        df_with_check.insert(0, "🗑️", False)
        
        # Настройка отображения
        column_config = {
            "🗑️": st.column_config.CheckboxColumn(label="", width=30, default=False)
        }
        edited_df = st.data_editor(
            df_with_check,
            column_config=column_config,
            width='stretch',
            hide_index=True,
            key=f"diagnostic_{key_suffix}"
        )
        
        # Кнопка удаления выбранных
        if st.button(f"🗑️ Удалить выбранные товары", key=f"del_selected_{key_suffix}"):
            selected_mask = edited_df["🗑️"] == True
            if selected_mask.any():
                ids_to_delete = edited_df.loc[selected_mask, df.columns[0]].tolist()
                confirm = st.checkbox(str(f"Подтвердить удаление {len(ids_to_delete)} товаров?"), key=f"confirm_{key_suffix}")
                if confirm:
                    try:
                        deleted = db.query(Product).filter(Product.id.in_(ids_to_delete)).delete(synchronize_session='fetch')
                        db.commit()
                        st.success(f"Удалено {deleted} товаров.")
                        st.rerun()
                    except Exception as e:
                        db.rollback()
                        st.error(f"Ошибка удаления: {e}")
            else:
                st.info("Нет выбранных товаров.")
    
    # --- CPU ---
    with cpu_tab:
        # Товары без характеристик
        type_cpu = db.query(ProductType).filter_by(name="CPU").first()
        if type_cpu:
            products_no_attrs = db.query(Product).filter(
                Product.type_id == type_cpu.id,
                ~Product.attribute_values.any()
            ).all()
            if products_no_attrs:
                df_no_attrs = pd.DataFrame([(p.id, p.name, p.url) for p in products_no_attrs],
                                           columns=["ID", "Name", "URL"])
                render_problem_table("CPU – без характеристик", df_no_attrs, [p.id for p in products_no_attrs], "cpu_no_attrs")
            else:
                st.success("✅ CPU – без характеристик: проблем нет!")
        
        # Товары без баллов PassMark
        if type_cpu:
            model_ids_with_scores = [row[0] for row in db.query(ModelScore.model_id).distinct().all()]
            products_no_scores = db.query(Product).filter(
                Product.type_id == type_cpu.id,
                Product.model_id.isnot(None),
                Product.model_id.notin_(model_ids_with_scores)
            ).all()
            if products_no_scores:
                df_no_scores = pd.DataFrame([(p.id, p.name, p.model.name if p.model else "Нет модели", p.url) for p in products_no_scores],
                                            columns=["ID", "Name", "Model Name", "URL"])
                render_problem_table("CPU – без баллов PassMark", df_no_scores, [p.id for p in products_no_scores], "cpu_no_scores")
            else:
                st.success("✅ CPU – без баллов PassMark: проблем нет!")
    
    # --- GPU ---
    with gpu_tab:
        type_gpu = db.query(ProductType).filter_by(name="GPU").first()
        if type_gpu:
            products_no_attrs = db.query(Product).filter(
                Product.type_id == type_gpu.id,
                ~Product.attribute_values.any()
            ).all()
            if products_no_attrs:
                df_no_attrs = pd.DataFrame([(p.id, p.name, p.url) for p in products_no_attrs],
                                           columns=["ID", "Name", "URL"])
                render_problem_table("GPU – без характеристик", df_no_attrs, [p.id for p in products_no_attrs], "gpu_no_attrs")
            else:
                st.success("✅ GPU – без характеристик: проблем нет!")
        
        if type_gpu:
            model_ids_with_scores = [row[0] for row in db.query(ModelScore.model_id).distinct().all()]
            products_no_scores = db.query(Product).filter(
                Product.type_id == type_gpu.id,
                Product.model_id.isnot(None),
                Product.model_id.notin_(model_ids_with_scores)
            ).all()
            if products_no_scores:
                df_no_scores = pd.DataFrame([(p.id, p.name, p.model.name if p.model else "Нет модели", p.url) for p in products_no_scores],
                                            columns=["ID", "Name", "Model Name", "URL"])
                render_problem_table("GPU – без баллов PassMark", df_no_scores, [p.id for p in products_no_scores], "gpu_no_scores")
            else:
                st.success("✅ GPU – без баллов PassMark: проблем нет!")

# ===========================
# 3. Графики (последние 30 дней)
# ===========================
elif selected_page == "Графики":
    cpu_tab, gpu_tab = st.tabs(["CPU", "GPU"])
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    def plot_product_history(component_type: str):
        type_obj = db.query(ProductType).filter_by(name=component_type).first()
        if not type_obj:
            st.warning(f"Нет данных для {component_type}")
            return
        
        products = db.query(Product).filter_by(type_id=type_obj.id).all()
        if not products:
            st.info(f"Нет продуктов типа {component_type}")
            return
        
        product_options = {p.name: p.id for p in products}
        selected_name = st.selectbox(f"Выберите {component_type}", list(product_options.keys()), key=f"select_{component_type}")
        selected_id = product_options[selected_name]
        selected_product = next(p for p in products if p.id == selected_id)
        
        # Цены
        prices = db.query(PriceHistory).filter(
            PriceHistory.product_id == selected_id,
            PriceHistory.timestamp >= thirty_days_ago
        ).order_by(PriceHistory.timestamp).all()
        df_price = pd.DataFrame([(p.timestamp, p.price) for p in prices], columns=["date", "price"])
        
        # Скоры
        scores = []
        if selected_product.model_id:
            scores = db.query(ModelScore).filter(
                ModelScore.model_id == selected_product.model_id,
                ModelScore.updated_at >= thirty_days_ago
            ).order_by(ModelScore.updated_at).all()
        df_score = pd.DataFrame([(s.updated_at, s.score) for s in scores], columns=["date", "score"])
        
        # Benefit
        benefits = db.query(BenefitHistory).filter(
            BenefitHistory.product_id == selected_id,
            BenefitHistory.timestamp >= thirty_days_ago
        ).order_by(BenefitHistory.timestamp).all()
        df_benefit = pd.DataFrame([(b.timestamp, b.benefit) for b in benefits], columns=["date", "benefit"])
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if not df_price.empty:
                fig_price = px.line(df_price, x="date", y="price", title="Цена", labels={"price": "₽"})
                st.plotly_chart(fig_price, width='stretch')
            else:
                st.info("Нет данных о ценах за последние 30 дней")
        with col2:
            if not df_score.empty:
                fig_score = px.line(df_score, x="date", y="score", title="PassMark Score", labels={"score": "баллы"})
                st.plotly_chart(fig_score, width='stretch')
            else:
                st.info("Нет данных о скорах за последние 30 дней")
        with col3:
            if not df_benefit.empty:
                fig_benefit = px.line(df_benefit, x="date", y="benefit", title="Benefit", labels={"benefit": "Benefit"})
                st.plotly_chart(fig_benefit, width='stretch')
            else:
                st.info("Нет данных о Benefit за последние 30 дней")
    
    with cpu_tab:
        plot_product_history("CPU")
    with gpu_tab:
        plot_product_history("GPU")

# ===========================
# 4. Аналитика (средние по дням)
# ===========================
elif selected_page == "Аналитика":
    cpu_tab, gpu_tab = st.tabs(["CPU", "GPU"])

    def get_type_id(component_type: str) -> Optional[int]:
        pt = db.query(ProductType).filter_by(name=component_type).first()
        return pt.id if pt else None

    def get_daily_averages(component_type: str):
        type_id = get_type_id(component_type)
        if type_id is None:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # Получаем все продукты данного типа
        products = db.query(Product).filter_by(type_id=type_id).all()
        product_ids = [p.id for p in products]
        if not product_ids:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # --- Средняя цена ---
        prices = db.query(PriceHistory).filter(PriceHistory.product_id.in_(product_ids)).all()
        df_price = pd.DataFrame([(p.timestamp.date(), p.price) for p in prices], columns=["date", "price"])
        if not df_price.empty:
            avg_price = df_price.groupby("date")["price"].mean().reset_index()
            avg_price.columns = ["date", "avg_price"]
        else:
            avg_price = pd.DataFrame(columns=["date", "avg_price"])

        # --- Средний балл PassMark ---
        # Собираем model_id всех продуктов
        model_ids = [p.model_id for p in products if p.model_id is not None]
        scores = db.query(ModelScore).filter(ModelScore.model_id.in_(model_ids)).all()
        df_score = pd.DataFrame([(s.updated_at.date(), s.score) for s in scores], columns=["date", "score"])
        if not df_score.empty:
            avg_score = df_score.groupby("date")["score"].mean().reset_index()
            avg_score.columns = ["date", "avg_score"]
        else:
            avg_score = pd.DataFrame(columns=["date", "avg_score"])

        # --- Средний Benefit ---
        benefits = db.query(BenefitHistory).filter(BenefitHistory.product_id.in_(product_ids)).all()
        df_benefit = pd.DataFrame([(b.timestamp.date(), b.benefit) for b in benefits], columns=["date", "benefit"])
        if not df_benefit.empty:
            avg_benefit = df_benefit.groupby("date")["benefit"].mean().reset_index()
            avg_benefit.columns = ["date", "avg_benefit"]
        else:
            avg_benefit = pd.DataFrame(columns=["date", "avg_benefit"])

        return avg_price, avg_score, avg_benefit

    def plot_trends(component_type: str):
        avg_price, avg_score, avg_benefit = get_daily_averages(component_type)
        if avg_price.empty and avg_score.empty and avg_benefit.empty:
            st.info(f"Нет данных для {component_type}")
            return

        col1, col2, col3 = st.columns(3)

        with col1:
            if not avg_price.empty:
                fig_price = px.line(avg_price, x="date", y="avg_price",
                                    title=f"Средняя цена {component_type}",
                                    labels={"avg_price": "₽", "date": "Дата"})
                st.plotly_chart(fig_price, width='stretch')
            else:
                st.info("Нет данных о ценах")

        with col2:
            if not avg_score.empty:
                fig_score = px.line(avg_score, x="date", y="avg_score",
                                    title=f"Средний балл PassMark {component_type}",
                                    labels={"avg_score": "баллы", "date": "Дата"})
                st.plotly_chart(fig_score, width='stretch')
            else:
                st.info("Нет данных о скорах")

        with col3:
            if not avg_benefit.empty:
                fig_benefit = px.line(avg_benefit, x="date", y="avg_benefit",
                                      title=f"Средний Benefit {component_type}",
                                      labels={"avg_benefit": "Benefit", "date": "Дата"})
                st.plotly_chart(fig_benefit, width='stretch')
            else:
                st.info("Нет данных о Benefit")

    with cpu_tab:
        plot_trends("CPU")
    with gpu_tab:
        plot_trends("GPU")

# ===========================
# 5. Подбор CPU/GPU
# ===========================
elif selected_page == "Подбор CPU/GPU":
    sub_tab1, sub_tab2 = st.tabs(["Подбор GPU под CPU", "Подбор CPU под GPU"])
    
    # Подбор GPU под выбранный CPU
    with sub_tab1:
        st.subheader("Выберите CPU, чтобы увидеть рекомендуемые GPU")
        cpu_type = db.query(ProductType).filter_by(name="CPU").first()
        gpu_type = db.query(ProductType).filter_by(name="GPU").first()
        if not cpu_type or not gpu_type:
            st.warning("Нет данных о CPU или GPU")
        else:
            # Получаем модели CPU с последним скором
            cpu_models = db.query(Model).filter_by(type_id=cpu_type.id).all()
            cpu_list = []
            for model in cpu_models:
                score = get_last_score(model.id)
                if score:
                    cpu_list.append((model.id, model.name, score))
            if not cpu_list:
                st.info("Нет CPU с баллами PassMark")
            else:
                selected_cpu_name = st.selectbox("Выберите CPU", [c[1] for c in cpu_list], key="cpu_select")
                selected_cpu = next(c for c in cpu_list if c[1] == selected_cpu_name)
                target_gpu_score = selected_cpu[2] * 1.25
                st.info(f"Целевой балл GPU: {target_gpu_score:.0f}")
                
                # Получаем все GPU с баллами, ценами и Benefit
                gpu_models = db.query(Model).filter_by(type_id=gpu_type.id).all()
                gpu_data = []
                for model in gpu_models:
                    score = get_last_score(model.id)
                    if not score:
                        continue
                    product = db.query(Product).filter_by(model_id=model.id).first()
                    price = get_last_price(product.id) if product else None
                    benefit = get_last_benefit(product.id) if product else None
                    gpu_data.append({
                        "Model Name": model.name,
                        "Score": score,
                        "Price (RUB)": price if price is not None else 0,
                        "Benefit": benefit if benefit is not None else 0,
                        "Deviation": abs(score - target_gpu_score) / target_gpu_score if target_gpu_score > 0 else 999
                    })
                df_gpu = pd.DataFrame(gpu_data)
                if not df_gpu.empty:
                    # Вычисляем процент Benefit относительно максимального в таблице
                    max_benefit = df_gpu['Benefit'].max()
                    if max_benefit > 0:
                        df_gpu['Benefit %'] = (df_gpu['Benefit'] / max_benefit * 100).round(1)
                    else:
                        df_gpu['Benefit %'] = 0
                    # Сортируем по отклонению (чем меньше, тем лучше)
                    df_gpu = df_gpu.sort_values(by="Deviation")
                    df_gpu["Match"] = df_gpu["Deviation"].apply(
                        lambda x: "⭐ Оптимально" if x < 0.2 else "👍 Хорошо" if x < 0.4 else "⚠️ Слабоват" if x > 0.6 else "👌 Приемлемо"
                    )
                    st.dataframe(df_gpu[["Model Name", "Score", "Price (RUB)", "Benefit", "Benefit %", "Match"]], width='stretch')
    
    # Подбор CPU под выбранный GPU
    with sub_tab2:
        st.subheader("Выберите GPU, чтобы увидеть рекомендуемые CPU")
        gpu_type = db.query(ProductType).filter_by(name="GPU").first()
        cpu_type = db.query(ProductType).filter_by(name="CPU").first()
        if not gpu_type or not cpu_type:
            st.warning("Нет данных о GPU или CPU")
        else:
            # Получаем модели GPU с последним скором
            gpu_models = db.query(Model).filter_by(type_id=gpu_type.id).all()
            gpu_list = []
            for model in gpu_models:
                score = get_last_score(model.id)
                if score:
                    gpu_list.append((model.id, model.name, score))
            if not gpu_list:
                st.info("Нет GPU с баллами PassMark")
            else:
                selected_gpu_name = st.selectbox("Выберите GPU", [g[1] for g in gpu_list], key="gpu_select")
                selected_gpu = next(g for g in gpu_list if g[1] == selected_gpu_name)
                target_cpu_score = selected_gpu[2] / 1.25
                st.info(f"Целевой балл CPU: {target_cpu_score:.0f}")
                
                # Получаем все CPU с баллами, ценами и Benefit
                cpu_models = db.query(Model).filter_by(type_id=cpu_type.id).all()
                cpu_data = []
                for model in cpu_models:
                    score = get_last_score(model.id)
                    if not score:
                        continue
                    product = db.query(Product).filter_by(model_id=model.id).first()
                    price = get_last_price(product.id) if product else None
                    benefit = get_last_benefit(product.id) if product else None
                    cpu_data.append({
                        "Model Name": model.name,
                        "Score": score,
                        "Price (RUB)": price if price is not None else 0,
                        "Benefit": benefit if benefit is not None else 0,
                        "Deviation": abs(score - target_cpu_score) / target_cpu_score if target_cpu_score > 0 else 999
                    })
                df_cpu = pd.DataFrame(cpu_data)
                if not df_cpu.empty:
                    max_benefit = df_cpu['Benefit'].max()
                    if max_benefit > 0:
                        df_cpu['Benefit %'] = (df_cpu['Benefit'] / max_benefit * 100).round(1)
                    else:
                        df_cpu['Benefit %'] = 0
                    df_cpu = df_cpu.sort_values(by="Deviation")
                    df_cpu["Match"] = df_cpu["Deviation"].apply(
                        lambda x: "⭐ Оптимально" if x < 0.2 else "👍 Хорошо" if x < 0.4 else "⚠️ Слабоват" if x > 0.6 else "👌 Приемлемо"
                    )
                    st.dataframe(df_cpu[["Model Name", "Score", "Price (RUB)", "Benefit", "Benefit %", "Match"]], width='stretch')

# ===========================
# 6. Тепловые карты (модели + конкретные товары)
# ===========================
elif selected_page == "Тепловые карты":  
    # Общие вспомогательные функции (модели CPU, чипы GPU)
    def get_cpu_models_data():
        cpu_type = db.query(ProductType).filter_by(name="CPU").first()
        if not cpu_type:
            return []
        cpu_models = db.query(Model).filter_by(type_id=cpu_type.id).all()
        cpu_data = []
        for model in cpu_models:
            score = get_last_score(model.id)
            if score is None:
                continue
            product = db.query(Product).filter_by(model_id=model.id).first()
            benefit = get_last_benefit(product.id) if product else None
            if benefit is None:
                benefit = 0.0
            cpu_data.append({
                "name": model.name,
                "score": score,
                "benefit": benefit
            })
        cpu_data.sort(key=lambda x: x["score"], reverse=True)
        return cpu_data

    def get_gpu_raw_values_data():
        gpu_attr = db.query(Attribute).filter_by(name="Графический процессор").first()
        if not gpu_attr:
            return []
        raw_values = db.query(AttributeValue.raw_value).filter_by(attribute_id=gpu_attr.id).distinct().all()
        raw_values = [rv[0] for rv in raw_values if rv[0]]
        result = []
        for raw_val in raw_values:
            product_ids = db.query(AttributeValue.product_id).filter(
                AttributeValue.attribute_id == gpu_attr.id,
                AttributeValue.raw_value == raw_val
            ).distinct().all()
            product_ids = [pid[0] for pid in product_ids]
            if not product_ids:
                continue
            model_ids = db.query(Product.model_id).filter(
                Product.id.in_(product_ids),
                Product.model_id.isnot(None)
            ).distinct().all()
            model_ids = [mid[0] for mid in model_ids]
            best_score = None
            for mid in model_ids:
                ms = db.query(ModelScore).filter_by(model_id=mid).order_by(ModelScore.updated_at.desc()).first()
                if ms and ms.score is not None and (best_score is None or ms.score > best_score):
                    best_score = ms.score
            if best_score is None:
                continue
            best_benefit = 0.0
            for pid in product_ids:
                bh = db.query(BenefitHistory).filter_by(product_id=pid).order_by(BenefitHistory.timestamp.desc()).first()
                if bh and bh.benefit is not None and bh.benefit > best_benefit:
                    best_benefit = bh.benefit
            result.append({
                "name": raw_val,
                "score": best_score,
                "benefit": best_benefit
            })
        result.sort(key=lambda x: x["score"], reverse=True)
        return result

    # --- Матричные вычисления для моделей ---
    @st.cache_data(ttl=3600)
    def compute_heatmap_benefit_models():
        cpus = get_cpu_models_data()
        gpus = get_gpu_raw_values_data()
        if not cpus or not gpus:
            return None, None, None
        cpu_names = [c["name"] for c in cpus]
        gpu_names = [g["name"] for g in gpus]
        matrix = []
        for cpu in cpus:
            row = []
            cpu_ben = cpu.get("benefit", 0.0) or 0.0
            for gpu in gpus:
                gpu_ben = gpu.get("benefit", 0.0) or 0.0
                product = (cpu_ben * gpu_ben) ** 0.1
                result = product if product >= 0 else 0.0
                row.append(result)
            matrix.append(row)
        return cpu_names, gpu_names, matrix

    @st.cache_data(ttl=3600)
    def compute_heatmap_optimal_models():
        cpus = get_cpu_models_data()
        gpus = get_gpu_raw_values_data()
        if not cpus or not gpus:
            return None, None, None
        cpu_names = [c["name"] for c in cpus]
        gpu_names = [g["name"] for g in gpus]
        matrix = []
        for cpu in cpus:
            row = []
            cpu_score = cpu["score"]
            if cpu_score is None or cpu_score <= 0:
                row = [0.0] * len(gpus)
                matrix.append(row)
                continue
            target = cpu_score * 1.25
            for gpu in gpus:
                gpu_score = gpu["score"]
                if gpu_score is None:
                    val = 0.0
                else:
                    diff = abs(target - gpu_score)
                    val = (1.0 / diff) ** 0.5 if diff != 0 else float('inf')
                row.append(val)
            matrix.append(row)
        return cpu_names, gpu_names, matrix

    @st.cache_data(ttl=3600)
    def compute_heatmap_combined_models():
        res_benefit = compute_heatmap_benefit_models()
        res_optimal = compute_heatmap_optimal_models()
        if res_benefit[0] is None or res_optimal[0] is None:
            return None, None, None
        cpu_names = res_benefit[0]
        gpu_names = res_benefit[1]
        benefit_mat = res_benefit[2]
        optimal_mat = res_optimal[2]
        combined = [[(benefit_mat[i][j] * optimal_mat[i][j]) ** 0.5 for j in range(len(gpu_names))] for i in range(len(cpu_names))]
        return cpu_names, gpu_names, combined

    # --- Отрисовка вкладок (модели) ---
    tab_models1, tab_models2, tab_models3 = st.tabs(["📊 Benefit (модели)", "🎯 Оптимальность (модели)", "🔗 Кривая подбора (модели)"])

    with tab_models1:
        cpu_names, gpu_names, mat = compute_heatmap_benefit_models()
        if cpu_names is None:
            st.warning("Недостаточно данных для Benefit (модели).")
        else:
            fig = px.imshow(mat, x=gpu_names, y=cpu_names,
                            labels=dict(x="GPU (чип)", y="CPU (модель)", color="√(Benefit)"),
                            title="Тепловая карта: √(Benefit_CPU × Benefit_GPU)",
                            color_continuous_scale="Viridis", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')

    with tab_models2:
        cpu_names, gpu_names, mat = compute_heatmap_optimal_models()
        if cpu_names is None:
            st.warning("Недостаточно данных для Оптимальности (модели).")
        else:
            fig = px.imshow(mat, x=gpu_names, y=cpu_names,
                            labels=dict(x="GPU (чип)", y="CPU (модель)", color="√(1/Δ)"),
                            title="Тепловая карта: √(1/|Score_CPU×1.25 - Score_GPU|)",
                            color_continuous_scale="Plasma", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')

    with tab_models3:
        cpu_names, gpu_names, mat = compute_heatmap_combined_models()
        if cpu_names is None:
            st.warning("Недостаточно данных для Кривой подбора (модели).")
        else:
            fig = px.imshow(mat, x=gpu_names, y=cpu_names,
                            labels=dict(x="GPU (чип)", y="CPU (модель)", color="Произведение"),
                            title="Тепловая карта: Benefit × Оптимальность",
                            color_continuous_scale="Viridis", aspect="auto", height=4800)
            st.plotly_chart(fig, width='stretch')