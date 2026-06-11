import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from dnsight.core.models import ProductType, Model, Product, Attribute, AttributeValue, PriceHistory
from dashboard.utils import get_last_score, get_last_benefit, get_delta_ratio


def get_best_product_price(db: Session, model_id: int) -> float:
    """Возвращает минимальную цену среди всех продуктов данной модели."""
    products = db.query(Product).filter_by(model_id=model_id).all()
    prices = []
    for prod in products:
        price = get_last_price(db, prod.id)
        if price:
            prices.append(price)
    return min(prices) if prices else 0.0


def get_best_gpu_price_for_raw(db: Session, raw_value: str) -> float:
    """Возвращает минимальную цену среди продуктов с указанным raw_value."""
    gpu_attr = db.query(Attribute).filter_by(name="Графический процессор").first()
    if not gpu_attr:
        return 0.0
    av_list = db.query(AttributeValue).filter_by(attribute_id=gpu_attr.id, raw_value=raw_value).all()
    product_ids = [av.product_id for av in av_list]
    prices = []
    for pid in product_ids:
        price = get_last_price(db, pid)
        if price:
            prices.append(price)
    return min(prices) if prices else 0.0


def get_last_price(db: Session, product_id: int):
    ph = db.query(PriceHistory).filter_by(product_id=product_id).order_by(PriceHistory.timestamp.desc()).first()
    return ph.price if ph else None


def render(db: Session):
    st.header("🖥️ ПК-подбор: оптимальные пары CPU + GPU")
    st.markdown("""
    Для каждого процессора показаны **три лучшие видеокарты** по комбинированной оценке **Combined** (кривая подбора).
    Комбинированная оценка учитывает Benefit, динамику Benefit и оптимальность производительности.
    """)

    # --- Получение данных о CPU и GPU ---
    cpu_type = db.query(ProductType).filter_by(name="CPU").first()
    gpu_type = db.query(ProductType).filter_by(name="GPU").first()
    if not cpu_type or not gpu_type:
        st.warning("Нет данных о CPU или GPU в базе.")
        return

    cpu_models = db.query(Model).filter_by(type_id=cpu_type.id).all()
    cpu_data = []
    for model in cpu_models:
        score = get_last_score(db, model.id)
        if score is None:
            continue
        product = db.query(Product).filter_by(model_id=model.id).first()
        if product:
            benefit = get_last_benefit(db, product.id)
            delta = get_delta_ratio(db, product.id)
            price = get_best_product_price(db, model.id)
        else:
            benefit = 0.0
            delta = 1.0
            price = 0.0
        cpu_data.append({
            "id": model.id,
            "name": model.name,
            "score": score,
            "benefit": benefit,
            "delta": delta,
            "price": price
        })
    if not cpu_data:
        st.info("Нет данных о CPU с баллами PassMark и ценой.")
        return

    # GPU – через raw_value
    gpu_attr = db.query(Attribute).filter_by(name="Графический процессор").first()
    if not gpu_attr:
        st.warning("Атрибут 'Графический процессор' не найден.")
        return
    raw_values = db.query(AttributeValue.raw_value).filter_by(attribute_id=gpu_attr.id).distinct().all()
    raw_values = [rv[0] for rv in raw_values if rv[0]]
    gpu_data = []
    for raw_val in raw_values:
        product_ids = db.query(AttributeValue.product_id).filter_by(attribute_id=gpu_attr.id, raw_value=raw_val).all()
        product_ids = [pid[0] for pid in product_ids]
        if not product_ids:
            continue
        model_ids = db.query(Product.model_id).filter(Product.id.in_(product_ids), Product.model_id.isnot(None)).distinct().all()
        model_ids = [mid[0] for mid in model_ids]
        best_score = None
        for mid in model_ids:
            sc = get_last_score(db, mid)
            if sc and (best_score is None or sc > best_score):
                best_score = sc
        if best_score is None:
            continue
        best_benefit = 0.0
        best_delta = 1.0
        for pid in product_ids:
            ben = get_last_benefit(db, pid)
            if ben and ben > best_benefit:
                best_benefit = ben
                best_delta = get_delta_ratio(db, pid)
        price = get_best_gpu_price_for_raw(db, raw_val)
        gpu_data.append({
            "name": raw_val,
            "score": best_score,
            "benefit": best_benefit,
            "delta": best_delta,
            "price": price
        })
    if not gpu_data:
        st.info("Нет данных о GPU с баллами PassMark и ценой.")
        return

    # --- Фильтры (применяются до группировки) ---
    st.subheader("Фильтры")
    col1, col2 = st.columns(2)
    with col1:
        min_score = st.number_input("Минимальная сумма баллов CPU+GPU", min_value=0, value=0, step=1000)
    with col2:
        max_price = st.number_input("Максимальная стоимость (₽)", min_value=0, value=500_000, step=10000)

    # --- Построение всех пар и фильтрация ---
    all_pairs = []
    for cpu in cpu_data:
        if cpu["price"] == 0:
            continue
        for gpu in gpu_data:
            if gpu["price"] == 0:
                continue
            total_score = cpu["score"] + gpu["score"]
            total_price = cpu["price"] + gpu["price"]
            if total_score < min_score or total_price > max_price:
                continue
            target = cpu["score"] * 1.25
            diff = abs(target - gpu["score"])
            optimal = 1.0 / diff if diff != 0 else float('inf')
            combined = cpu["benefit"] * gpu["benefit"] * cpu["delta"] * gpu["delta"] * optimal
            if combined == float('inf'):
                combined = 1e9
            pair_benefit = cpu["benefit"] * gpu["benefit"]
            all_pairs.append({
                "CPU": cpu["name"],
                "GPU": gpu["name"],
                "Сумма баллов": total_score,
                "Стоимость (₽)": total_price,
                "Benefit пары": pair_benefit,
                "Combined": combined,
                "cpu_score": cpu["score"],  # для возможной сортировки
            })

    if not all_pairs:
        st.warning("Нет пар, удовлетворяющих условиям фильтра.")
        return

    # --- Группировка: для каждого CPU оставляем топ-3 GPU по Combined ---
    cpu_groups = {}
    for pair in all_pairs:
        cpu_name = pair["CPU"]
        if cpu_name not in cpu_groups:
            cpu_groups[cpu_name] = []
        cpu_groups[cpu_name].append(pair)

    # Сортируем пары внутри каждого CPU по Combined (убывание) и берём первые 3
    top_pairs = []
    for cpu_name, pairs in cpu_groups.items():
        sorted_pairs = sorted(pairs, key=lambda x: x["Combined"], reverse=True)
        top_pairs.extend(sorted_pairs[:3])

    # Дополнительная глобальная сортировка (опционально) – можно отсортировать процессоры по лучшему Combined их топ-3
    # Сначала сгруппируем по CPU и возьмём максимальный Combined среди топ-3, затем отсортируем процессоры
    cpu_best_combined = {}
    for pair in top_pairs:
        cpu = pair["CPU"]
        if cpu not in cpu_best_combined or pair["Combined"] > cpu_best_combined[cpu]:
            cpu_best_combined[cpu] = pair["Combined"]
    sorted_cpus = sorted(cpu_best_combined.keys(), key=lambda x: cpu_best_combined[x], reverse=True)

    # Пересобираем top_pairs в порядке отсортированных CPU и внутри каждого CPU пары уже отсортированы
    final_pairs = []
    for cpu in sorted_cpus:
        # берём первые 3 пары для этого CPU из ранее созданного списка
        # Чтобы избежать потери порядка, можно заново отфильтровать top_pairs
        cpu_pairs = [p for p in top_pairs if p["CPU"] == cpu]
        # они уже отсортированы по Combined убыванию, потому что мы добавляли из sorted_pairs[:3]
        final_pairs.extend(cpu_pairs)

    df = pd.DataFrame(final_pairs)

    st.subheader(f"Топ-3 видеокарты для каждого процессора (всего {len(df)} записей)")
    st.dataframe(
        df[["CPU", "GPU", "Сумма баллов", "Стоимость (₽)", "Benefit пары", "Combined"]],
        width='stretch'
    )