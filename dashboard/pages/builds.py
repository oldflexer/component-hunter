import streamlit as st
import pandas as pd
import re
import math
from sqlalchemy.orm import Session
from dnsight.core.models import ProductType, Model, Product, Attribute, AttributeValue, PriceHistory
from dashboard.utils import get_last_score, get_last_benefit, get_delta_ratio, get_last_price


def get_best_product_price(db: Session, model_id: int) -> float:
    products = db.query(Product).filter_by(model_id=model_id).all()
    prices = []
    for prod in products:
        price = get_last_price(db, prod.id)
        if price:
            prices.append(price)
    return min(prices) if prices else 0.0


def get_best_gpu_price_for_raw(db: Session, raw_value: str) -> float:
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


def extract_pcie_version(pcie_str: str) -> float:
    if not pcie_str:
        return 0.0
    match = re.search(r'(\d+\.?\d*)', pcie_str)
    return float(match.group(1)) if match else 0.0


def extract_first_number(value: str) -> int:
    match = re.search(r'\d+', value)
    return int(match.group()) if match else 0


def extract_tdp(value: str) -> int:
    match = re.search(r'\d+', value)
    return int(match.group()) if match else 0


def get_cpu_socket_data(db: Session):
    cpu_type = db.query(ProductType).filter_by(name="CPU").first()
    if not cpu_type:
        return []
    cpu_models = db.query(Model).filter_by(type_id=cpu_type.id).all()
    result = []
    for model in cpu_models:
        score = get_last_score(db, model.id)
        if score is None:
            continue
        product = db.query(Product).filter_by(model_id=model.id).first()
        if not product:
            continue
        benefit = get_last_benefit(db, product.id) or 0.0
        attrs = db.query(AttributeValue).filter_by(product_id=product.id).all()
        attr_dict = {av.attribute.name: av.raw_value for av in attrs}
        socket = attr_dict.get("Сокет")
        tdp_raw = attr_dict.get("Тепловыделение (TDP)")
        tdp = extract_tdp(tdp_raw) if tdp_raw else 0
        if not socket:
            continue
        result.append({
            "name": model.name,
            "benefit": benefit,
            "socket": socket.strip(),
            "tdp": tdp,
        })
    return result


def get_mb_socket_data(db: Session):
    mb_type = db.query(ProductType).filter_by(name="Motherboard").first()
    if not mb_type:
        return []
    mb_products = db.query(Product).filter_by(type_id=mb_type.id).all()
    result = []
    for prod in mb_products:
        benefit = get_last_benefit(db, prod.id) or 0.0
        attrs = db.query(AttributeValue).filter_by(product_id=prod.id).all()
        attr_dict = {av.attribute.name: av.raw_value for av in attrs}
        socket = attr_dict.get("Сокет")
        phase_raw = attr_dict.get("Количество фаз питания")
        phase = extract_first_number(phase_raw) if phase_raw else 0
        if not socket:
            continue
        display_name = None
        if prod.model_id:
            model = db.query(Model).filter_by(id=prod.model_id).first()
            if model:
                display_name = model.name
        if not display_name:
            display_name = attr_dict.get("Модель")
        if not display_name:
            display_name = prod.name
        result.append({
            "name": display_name,
            "benefit": benefit,
            "socket": socket.strip(),
            "phase": phase,
        })
    return result


def calculate_combined_cpu_mb(cpu_benefit, mb_benefit, cpu_tdp, mb_phase):
    if cpu_tdp == 0 or mb_phase == 0:
        return 0.0
    diff = abs(cpu_tdp / 10.58 - mb_phase)
    if diff == 0:
        power = 1e9
    else:
        power = (1.0 / diff) ** 0.5
    combined = (cpu_benefit * mb_benefit * power) ** 0.5
    return combined


def render_cpu_gpu_tab(db: Session):
    st.header("Подбор CPU + GPU")
    st.markdown("""
    Для каждого процессора показаны **три лучшие видеокарты** по комбинированной оценке **Combined** (кривая подбора).
    Комбинированная оценка учитывает Benefit, динамику Benefit и оптимальность производительности.
    """)
    # Чекбокс для будущего использования
    st.checkbox("Учитывать версию PCI-E (в разработке)", key="use_pcie_gpu", value=False)

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

    col1, col2 = st.columns(2)
    with col1:
        min_score = st.number_input("Минимальная сумма баллов CPU+GPU", min_value=0, value=0, step=1000)
    with col2:
        max_price = st.number_input("Максимальная стоимость (₽)", min_value=0, value=500_000, step=10000)

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
            })

    if not all_pairs:
        st.warning("Нет пар, удовлетворяющих условиям фильтра.")
        return

    cpu_groups = {}
    for pair in all_pairs:
        cpu_name = pair["CPU"]
        if cpu_name not in cpu_groups:
            cpu_groups[cpu_name] = []
        cpu_groups[cpu_name].append(pair)

    top_pairs = []
    for cpu_name, pairs in cpu_groups.items():
        sorted_pairs = sorted(pairs, key=lambda x: x["Combined"], reverse=True)
        top_pairs.extend(sorted_pairs[:3])

    cpu_best_combined = {}
    for pair in top_pairs:
        cpu = pair["CPU"]
        if cpu not in cpu_best_combined or pair["Combined"] > cpu_best_combined[cpu]:
            cpu_best_combined[cpu] = pair["Combined"]
    sorted_cpus = sorted(cpu_best_combined.keys(), key=lambda x: cpu_best_combined[x], reverse=True)

    final_pairs = []
    for cpu in sorted_cpus:
        cpu_pairs = [p for p in top_pairs if p["CPU"] == cpu]
        final_pairs.extend(cpu_pairs)

    df = pd.DataFrame(final_pairs)
    st.subheader(f"Топ-3 видеокарты для каждого процессора (всего {len(df)} записей)")
    st.dataframe(df[["CPU", "GPU", "Сумма баллов", "Стоимость (₽)", "Benefit пары", "Combined"]], width='stretch')


def render_cpu_mb_tab(db: Session):
    st.header("Подбор CPU + Motherboard")
    st.markdown("""
    Для каждого процессора показаны **три самые выгодные материнские платы** по комбинированной оценке **Combined** (кривая подбора CPU×MB).
    Оценка учитывает Benefit CPU, Benefit MB и энергоэффективность (TDP vs фазы питания).
    """)

    # Получаем данные CPU и MB
    cpus = get_cpu_socket_data(db)
    mbs = get_mb_socket_data(db)
    if not cpus or not mbs:
        st.info("Недостаточно данных для подбора (нет CPU или MB с сокетом).")
        return

    # Группируем MB по сокету для быстрого доступа
    mb_by_socket = {}
    for mb in mbs:
        socket = mb["socket"]
        if socket not in mb_by_socket:
            mb_by_socket[socket] = []
        mb_by_socket[socket].append(mb)

    # Для каждого CPU собираем совместимые MB и вычисляем Combined
    all_pairs = []
    for cpu in cpus:
        socket = cpu["socket"]
        if socket not in mb_by_socket:
            continue
        for mb in mb_by_socket[socket]:
            combined = calculate_combined_cpu_mb(cpu["benefit"], mb["benefit"], cpu["tdp"], mb["phase"])
            all_pairs.append({
                "CPU": cpu["name"],
                "Motherboard": mb["name"],
                "Combined": combined,
                "Benefit CPU": cpu["benefit"],
                "Benefit MB": mb["benefit"],
                "TDP": cpu["tdp"],
                "Phase": mb["phase"],
                "Socket": socket,
            })

    if not all_pairs:
        st.warning("Нет совместимых пар CPU+MB.")
        return

    # Группировка по CPU, выбор топ-3 по Combined
    cpu_groups = {}
    for pair in all_pairs:
        cpu_name = pair["CPU"]
        if cpu_name not in cpu_groups:
            cpu_groups[cpu_name] = []
        cpu_groups[cpu_name].append(pair)

    top_pairs = []
    for cpu_name, pairs in cpu_groups.items():
        sorted_pairs = sorted(pairs, key=lambda x: x["Combined"], reverse=True)
        top_pairs.extend(sorted_pairs[:3])

    # Сортировка по убыванию Combined
    top_pairs.sort(key=lambda x: x["Combined"], reverse=True)

    df = pd.DataFrame(top_pairs)
    st.subheader(f"Топ-3 материнские платы для каждого процессора (всего {len(df)} записей)")
    st.dataframe(df[["CPU", "Motherboard", "Combined", "Benefit CPU", "Benefit MB", "TDP", "Phase", "Socket"]], width='stretch')


def render(db: Session):
    tabs = st.tabs(["CPU+GPU", "CPU+MB"])
    with tabs[0]:
        render_cpu_gpu_tab(db)
    with tabs[1]:
        render_cpu_mb_tab(db)