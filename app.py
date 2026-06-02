import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import time
import plotly.express as px
from datetime import datetime, timedelta
from sqlalchemy import func, and_

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
    
    selected_page = st.selectbox(
        "Выберите раздел",
        ["Таблицы", "Диагностика", "Графики", "Подбор CPU/GPU", "Тепловые карты"]
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
# 1. Таблицы (без изменений)
# ===========================
if selected_page == "Таблицы":
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
        ["product_types", "models", "model_scores", "products",
         "attributes", "attribute_values", "price_history", "benefit_history"]
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

# ===========================
# 2. Диагностика (исправлено)
# ===========================
elif selected_page == "Диагностика":
    cpu_tab, gpu_tab = st.tabs(["CPU", "GPU"])
    
    def get_products_without_attributes(component_type_name: str) -> pd.DataFrame:
        type_obj = db.query(ProductType).filter_by(name=component_type_name).first()
        if not type_obj:
            return pd.DataFrame()
        products = db.query(Product).filter(
            Product.type_id == type_obj.id,
            ~Product.attribute_values.any()
        ).all()
        if products:
            return pd.DataFrame([(p.id, p.name, p.url) for p in products],
                                columns=["ID", "Name", "URL"])
        return pd.DataFrame()

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
            st.success("✅ Все CPU имеют характеристики. Проблем нет!")
        
        st.subheader("CPU – без баллов PassMark")
        df_no_scores = get_products_without_scores("CPU")
        if not df_no_scores.empty:
            st.dataframe(df_no_scores, width='stretch')
        else:
            st.success("✅ Все CPU имеют баллы PassMark. Проблем нет!")

    with gpu_tab:
        st.subheader("GPU – без характеристик")
        df_no_attrs = get_products_without_attributes("GPU")
        if not df_no_attrs.empty:
            st.dataframe(df_no_attrs, width='stretch')
        else:
            st.success("✅ Все GPU имеют характеристики. Проблем нет!")
        
        st.subheader("GPU – без баллов PassMark")
        df_no_scores = get_products_without_scores("GPU")
        if not df_no_scores.empty:
            st.dataframe(df_no_scores, width='stretch')
        else:
            st.success("✅ Все GPU имеют баллы PassMark. Проблем нет!")

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
                st.plotly_chart(fig_price, use_container_width=True)
            else:
                st.info("Нет данных о ценах за последние 30 дней")
        with col2:
            if not df_score.empty:
                fig_score = px.line(df_score, x="date", y="score", title="PassMark Score", labels={"score": "баллы"})
                st.plotly_chart(fig_score, use_container_width=True)
            else:
                st.info("Нет данных о скорах за последние 30 дней")
        with col3:
            if not df_benefit.empty:
                fig_benefit = px.line(df_benefit, x="date", y="benefit", title="Benefit", labels={"benefit": "Benefit"})
                st.plotly_chart(fig_benefit, use_container_width=True)
            else:
                st.info("Нет данных о Benefit за последние 30 дней")
    
    with cpu_tab:
        plot_product_history("CPU")
    with gpu_tab:
        plot_product_history("GPU")

# ===========================
# 4. Подбор CPU/GPU
# ===========================
elif selected_page == "Подбор CPU/GPU":
    sub_tab1, sub_tab2 = st.tabs(["Подбор GPU под CPU", "Подбор CPU под GPU"])
    
    # Подбор GPU под выбранный CPU
    with sub_tab1:
        st.subheader("Выберите CPU, чтобы увидеть рекомендуемые GPU")
        # Получаем все CPU с актуальными скорами
        cpu_type = db.query(ProductType).filter_by(name="CPU").first()
        gpu_type = db.query(ProductType).filter_by(name="GPU").first()
        if not cpu_type or not gpu_type:
            st.warning("Нет данных о CPU или GPU")
        else:
            # Получаем модели CPU (уникальные) с последним скором
            cpu_models = db.query(Model).filter_by(type_id=cpu_type.id).all()
            cpu_list = []
            for model in cpu_models:
                score = get_last_score(model.id)
                if score:
                    cpu_list.append((model.id, model.name, score))
            if not cpu_list:
                st.info("Нет CPU с баллами PassMark")
            else:
                selected_cpu_name = st.selectbox("Выберите CPU", [c[1] for c in cpu_list])
                selected_cpu = next(c for c in cpu_list if c[1] == selected_cpu_name)
                target_gpu_score = selected_cpu[2] * 1.5
                st.info(f"Целевой балл GPU: {target_gpu_score:.0f}")
                
                # Получаем все GPU с последними скорами и ценами
                gpu_models = db.query(Model).filter_by(type_id=gpu_type.id).all()
                gpu_data = []
                for model in gpu_models:
                    score = get_last_score(model.id)
                    if not score:
                        continue
                    # Берём один продукт этой модели (можно среднюю цену, но возьмём первый)
                    product = db.query(Product).filter_by(model_id=model.id).first()
                    price = get_last_price(product.id) if product else None
                    benefit = get_last_benefit(product.id) if product else None
                    gpu_data.append({
                        "Model Name": model.name,
                        "Score": score,
                        "Price (RUB)": price if price else "N/A",
                        "Benefit": benefit if benefit else "N/A",
                        "Deviation": abs(score - target_gpu_score) / target_gpu_score
                    })
                df_gpu = pd.DataFrame(gpu_data)
                if not df_gpu.empty and 'Benefit' in df_gpu.columns:
                    max_benefit = df_gpu['Benefit'].max()
                    if max_benefit and max_benefit > 0:
                        df_gpu['Benefit %'] = (df_gpu['Benefit'] / max_benefit * 100).round(1)
                    else:
                        df_gpu['Benefit %'] = 0
                # Сортируем по отклонению
                df_gpu = df_gpu.sort_values(by="Deviation")
                df_gpu["Match"] = df_gpu["Deviation"].apply(lambda x: "⭐ Оптимально" if x < 0.2 else "👍 Хорошо" if x < 0.4 else "⚠️ Слабоват" if x > 0.6 else "👌 Приемлемо")
                st.dataframe(df_gpu[["Model Name", "Score", "Price (RUB)", "Benefit", "Benefit %", "Match"]], width='stretch')

    # Подбор CPU под выбранный GPU
    with sub_tab2:
        st.subheader("Выберите GPU, чтобы увидеть рекомендуемые CPU")
        if not gpu_type or not cpu_type:
            st.warning("Нет данных о GPU или CPU")
        else:
            gpu_models = db.query(Model).filter_by(type_id=gpu_type.id).all()
            gpu_list = []
            for model in gpu_models:
                score = get_last_score(model.id)
                if score:
                    gpu_list.append((model.id, model.name, score))
            if not gpu_list:
                st.info("Нет GPU с баллами PassMark")
            else:
                selected_gpu_name = st.selectbox("Выберите GPU", [g[1] for g in gpu_list])
                selected_gpu = next(g for g in gpu_list if g[1] == selected_gpu_name)
                target_cpu_score = selected_gpu[2] / 1.5
                st.info(f"Целевой балл CPU: {target_cpu_score:.0f}")
                
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
                        "Price (RUB)": price if price else "N/A",
                        "Benefit": benefit if benefit else "N/A",
                        "Deviation": abs(score - target_cpu_score) / target_cpu_score
                    })
                df_cpu = pd.DataFrame(cpu_data).sort_values(by="Deviation")
                if not df_cpu.empty and 'Benefit' in df_cpu.columns:
                    max_benefit = df_cpu['Benefit'].max()
                    if max_benefit and max_benefit > 0:
                        df_cpu['Benefit %'] = (df_cpu['Benefit'] / max_benefit * 100).round(1)
                    else:
                        df_cpu['Benefit %'] = 0
                df_cpu = df_cpu.sort_values(by="Deviation")
                df_cpu["Match"] = df_cpu["Deviation"].apply(lambda x: "⭐ Оптимально" if x < 0.2 else "👍 Хорошо" if x < 0.4 else "⚠️ Слабоват" if x > 0.6 else "👌 Приемлемо")
                st.dataframe(df_cpu[["Model Name", "Score", "Price (RUB)", "Benefit", "Benefit %", "Match"]], width='stretch')

# ===========================
# 5. Тепловые карты (все модели)
# ===========================
elif selected_page == "Тепловые карты":
    heat_tab1, heat_tab2 = st.tabs(["Benefit CPU+GPU", "Оптимальные CPU+GPU"])
    
    # Получаем все модели CPU и GPU с их последними баллами и Benefit (для любого продукта этой модели)
    def get_all_models_data():
        cpu_type = db.query(ProductType).filter_by(name="CPU").first()
        gpu_type = db.query(ProductType).filter_by(name="GPU").first()
        if not cpu_type or not gpu_type:
            return [], []
        cpu_models = db.query(Model).filter_by(type_id=cpu_type.id).all()
        gpu_models = db.query(Model).filter_by(type_id=gpu_type.id).all()
        cpu_data = []
        for model in cpu_models:
            score = get_last_score(model.id)
            if score is None:
                continue
            product = db.query(Product).filter_by(model_id=model.id).first()
            benefit = get_last_benefit(product.id) if product else None
            cpu_data.append({
                "id": model.id,
                "name": model.name,
                "score": score,
                "benefit": benefit if benefit else 0
            })
        gpu_data = []
        for model in gpu_models:
            score = get_last_score(model.id)
            if score is None:
                continue
            product = db.query(Product).filter_by(model_id=model.id).first()
            benefit = get_last_benefit(product.id) if product else None
            gpu_data.append({
                "id": model.id,
                "name": model.name,
                "score": score,
                "benefit": benefit if benefit else 0
            })
        # Сортировка по убыванию баллов
        cpu_data.sort(key=lambda x: x["score"], reverse=True)
        gpu_data.sort(key=lambda x: x["score"], reverse=True)
        return cpu_data, gpu_data
    
    @st.cache_data(ttl=3600)
    def compute_heatmap_data():
        cpus, gpus = get_all_models_data()
        if not cpus or not gpus:
            return None, None, None, None  # 4 значения вместо 3
        cpu_names = [c["name"] for c in cpus]
        gpu_names = [g["name"] for g in gpus]
        benefit_matrix = []
        optimal_matrix = []
        for cpu in cpus:
            benefit_row = []
            optimal_row = []
            for gpu in gpus:
                avg_benefit = (cpu["benefit"] + gpu["benefit"]) / 2 if cpu["benefit"] and gpu["benefit"] else 0
                benefit_row.append(avg_benefit)
                target = cpu["score"] * 1.5
                if target == 0:
                    deviation = 0
                else:
                    deviation = min(gpu["score"], target) / max(gpu["score"], target)
                optimal_value = avg_benefit * deviation
                optimal_row.append(optimal_value)
            benefit_matrix.append(benefit_row)
            optimal_matrix.append(optimal_row)
        return cpu_names, gpu_names, benefit_matrix, optimal_matrix

    # Вызов и проверка
    cpu_names, gpu_names, benefit_mat, optimal_mat = compute_heatmap_data()
    if cpu_names is None or gpu_names is None:
        st.warning("Недостаточно данных для построения тепловых карт. Убедитесь, что у моделей есть скоры и Benefit.")
    else:
        with heat_tab1:
            fig = px.imshow(benefit_mat,
                            x=gpu_names,
                            y=cpu_names,
                            labels=dict(x="GPU", y="CPU", color="Средний Benefit"),
                            title="Тепловая карта среднего Benefit (CPU × GPU)",
                            color_continuous_scale="Viridis",
                            aspect="auto",
                            height=800)
            st.plotly_chart(fig, use_container_width=True)
        
        with heat_tab2:
            fig2 = px.imshow(optimal_mat,
                            x=gpu_names,
                            y=cpu_names,
                            labels=dict(x="GPU", y="CPU", color="Оптимальность"),
                            title="Тепловая карта оптимальности пар CPU–GPU (с учётом целевого балла)",
                            color_continuous_scale="Plasma",
                            aspect="auto",
                            height=800)
            st.plotly_chart(fig2, use_container_width=True)