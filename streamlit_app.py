from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st


APP_TITLE = "NPS Galaxia"
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DRIVE_URL = "https://drive.google.com/drive/folders/1JcQyaMxXY4ZcRooXPgWGZ5QjWXUHzsil?usp=drive_link"
DEFAULT_PLAN_API_URL = "https://script.google.com/macros/s/AKfycbzAW3Cq82gjIEVZq25mExuEUpc2ZgEFlq9DSsLOonqaQUK7DV7_cAnCcVwAJqCw3pVPPw/exec"


def secret_or_env(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.environ.get(name, default)).strip()


def truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "si", "sí", "y"}


def key(value: object) -> str:
    text = str(value or "").strip().lower()
    return (
        text.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
        .replace("_", " ")
    )


def norm_code(value: object) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits.lstrip("0") or digits


def first_col(df: pd.DataFrame, options: list[str]) -> str | None:
    keys = {key(col): col for col in df.columns}
    for option in options:
        option_key = key(option)
        if option_key in keys:
            return keys[option_key]
    for option in options:
        option_key = key(option)
        for k, col in keys.items():
            if option_key in k:
                return col
    return None


def read_sheet_with_detected_header(path: Path, sheet: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet, header=None, dtype="string")
    if raw.empty:
        return pd.DataFrame()
    header_index = raw.head(20).notna().sum(axis=1).astype(int).idxmax()
    headers = raw.iloc[header_index].fillna("").astype(str).str.strip().tolist()
    used: dict[str, int] = {}
    clean_headers = []
    for idx, header in enumerate(headers):
        name = header or f"Column_{idx + 1}"
        used[name] = used.get(name, 0) + 1
        clean_headers.append(name if used[name] == 1 else f"{name} {used[name]}")
    data = raw.iloc[header_index + 1 :].copy()
    data.columns = clean_headers
    data = data.dropna(how="all")
    return data


def download_drive_folder() -> Path | None:
    url = secret_or_env("GOOGLE_DRIVE_NPS_URL", DEFAULT_DRIVE_URL)
    target = PROJECT_ROOT / ".cloud_data" / "nps"
    refresh = truthy(secret_or_env("FORCE_GDRIVE_REFRESH", "false"))
    if target.exists() and any(target.iterdir()) and not refresh:
        return target

    try:
        import gdown
    except ImportError:
        st.error("Falta instalar gdown. Revisar requirements.txt.")
        return None

    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        gdown.download_folder(url=url, output=str(target), quiet=True, use_cookies=False)
    except Exception as exc:
        st.error(f"No pude descargar Google Drive: {exc}")
        return None
    return target if target.exists() and any(target.iterdir()) else None


def pick_file(folder: Path, include: list[str]) -> Path | None:
    candidates = []
    for path in folder.glob("*.xls*"):
        name = key(path.name)
        if all(term in name for term in include):
            candidates.append(path)
    return max(candidates, key=lambda p: p.stat().st_mtime, default=None)


@st.cache_data(show_spinner=False)
def load_nps_data(refresh_key: str) -> tuple[pd.DataFrame, dict[str, object]]:
    folder = download_drive_folder()
    if folder is None:
        return pd.DataFrame(), {"error": "No se pudo descargar Drive"}

    nps_file = pick_file(folder, ["nps"])
    client_file = pick_file(folder, ["plantilla"]) or pick_file(folder, ["cliente"])
    if nps_file is None:
        return pd.DataFrame(), {"error": "No se encontro archivo NPS"}

    nps_sheets = pd.ExcelFile(nps_file).sheet_names
    nps_frames = {sheet: read_sheet_with_detected_header(nps_file, sheet) for sheet in nps_sheets}
    nps_sheet, nps_df = next(
        (
            (name, df)
            for name, df in nps_frames.items()
            if first_col(df, ["score"]) and first_col(df, ["fecha_enc", "fecha"])
        ),
        (nps_sheets[0], nps_frames[nps_sheets[0]]),
    )

    client_df = pd.DataFrame()
    route_df = pd.DataFrame()
    client_sheet = "No detectada"
    route_sheet = "No detectada"
    if client_file is not None:
        for sheet in pd.ExcelFile(client_file).sheet_names:
            df = read_sheet_with_detected_header(client_file, sheet)
            if first_col(df, ["cliente"]) and first_col(df, ["codigo ruta vta", "ruta"]):
                client_df = df
                client_sheet = sheet
            if "ruta" in key(sheet) and first_col(df, ["codigo"]) and first_col(df, ["vendedor"]):
                route_df = df
                route_sheet = sheet

    rows = normalize_nps(nps_df, client_df, route_df)
    meta = {
        "nps_file": nps_file.name,
        "nps_sheet": nps_sheet,
        "client_file": client_file.name if client_file else "No detectado",
        "client_sheet": client_sheet,
        "route_sheet": route_sheet,
        "folder": str(folder),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return rows, meta


def normalize_nps(nps: pd.DataFrame, clients: pd.DataFrame, routes: pd.DataFrame) -> pd.DataFrame:
    fecha_col = first_col(nps, ["fecha_enc", "fecha enc", "fecha"])
    score_col = first_col(nps, ["score"])
    full_client_col = first_col(nps, ["cod_cliente_distribuidor_activo", "cod cliente distribuidor activo"])
    dist_col = first_col(nps, ["cod_distribuidor", "cod distribuidor"])
    name_col = first_col(nps, ["nombre_cliente", "nombre cliente"])
    driver_col = first_col(nps, ["primer_driver", "driver primario"])
    subdriver_col = first_col(nps, ["secondary_driver", "driver secundario"])
    comment_col = first_col(nps, ["comentario"])
    ddc_col = first_col(nps, ["ddc_name", "ddc name"])
    localidad_col = first_col(nps, ["desc_localidad", "localidad"])

    client_lookup: dict[str, dict[str, object]] = {}
    route_lookup: dict[str, dict[str, object]] = {}
    if not clients.empty:
        c_code = first_col(clients, ["cliente"])
        c_route = first_col(clients, ["codigo ruta vta", "ruta"])
        c_name = first_col(clients, ["razon social", "nombre de fantasia", "cliente"])
        if c_code and c_route:
            for _, row in clients.iterrows():
                client_lookup[norm_code(row.get(c_code))] = {
                    "route": norm_code(row.get(c_route)),
                    "name": str(row.get(c_name, "") or "").strip() if c_name else "",
                }
    if not routes.empty:
        r_code = first_col(routes, ["codigo"])
        r_vendor = first_col(routes, ["vendedor"])
        r_desc = first_col(routes, ["descripcion"])
        if r_code:
            for _, row in routes.iterrows():
                route_lookup[norm_code(row.get(r_code))] = {
                    "promotor": str(row.get(r_vendor, "") or "").strip() if r_vendor else "",
                    "ruta": str(row.get(r_desc, "") or "").strip() if r_desc else "",
                }

    out = []
    for idx, row in nps.iterrows():
        score = pd.to_numeric(row.get(score_col), errors="coerce") if score_col else pd.NA
        if pd.isna(score) or score < 0 or score > 10:
            continue
        date = pd.to_datetime(row.get(fecha_col), errors="coerce", dayfirst=True) if fecha_col else pd.NaT
        full_client = str(row.get(full_client_col, "") or "") if full_client_col else ""
        distributor = norm_code(row.get(dist_col)) if dist_col else ""
        client_digits = norm_code(full_client)
        if distributor and client_digits.startswith(distributor):
            client_digits = norm_code(client_digits[len(distributor) :])
        client = client_lookup.get(client_digits, {})
        route = route_lookup.get(client.get("route", ""), {})
        tipo = "Detractor" if score <= 6 else "Pasivo" if score <= 8 else "Promotor"
        out.append(
            {
                "id": idx + 1,
                "fecha": date,
                "mes": date.strftime("%Y-%m") if pd.notna(date) else "Sin fecha",
                "cliente_codigo": client_digits,
                "cliente": str(row.get(name_col, "") or client.get("name") or client_digits or "Sin cliente").strip(),
                "score": float(score),
                "tipo_nps": tipo,
                "driver": str(row.get(driver_col, "") or "Sin driver").strip(),
                "subdriver": str(row.get(subdriver_col, "") or "Sin subdriver").strip(),
                "comentario": str(row.get(comment_col, "") or "").strip(),
                "promotor": str(route.get("promotor") or row.get(ddc_col, "") or "Sin promotor").strip(),
                "ruta": str(route.get("ruta") or "").strip(),
                "localidad": str(row.get(localidad_col, "") or "").strip(),
                "matched_client": bool(client),
                "matched_route": bool(route),
            }
        )
    return pd.DataFrame(out)


def nps_score(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    promoters = (df["tipo_nps"] == "Promotor").mean()
    detractors = (df["tipo_nps"] == "Detractor").mean()
    return float((promoters - detractors) * 100)


def pct_value(numerator: int | float, denominator: int | float) -> float:
    return float(numerator / denominator * 100) if denominator else 0.0


def filtered_unique_surveys(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    dedupe_cols = [col for col in ["fecha", "cliente_codigo", "score"] if col in df.columns]
    return df.drop_duplicates(dedupe_cols) if dedupe_cols else df.drop_duplicates()


def pain_point(row: pd.Series) -> bool:
    text = f"{row.get('subdriver', '')} {row.get('comentario', '')}".lower()
    negative_terms = [
        "no ",
        "sin ",
        "problema",
        "falla",
        "demora",
        "incorrect",
        "pendiente",
        "reclamo",
        "faltante",
        "malo",
        "difícil",
        "dificil",
        "tarde",
        "nunca",
    ]
    neutral = {"", "ninguno", "sin comentario", "na", "n/a", "null"}
    return text.strip() not in neutral and any(term in text for term in negative_terms)


def priority_for(row: pd.Series) -> str:
    if row.get("tipo_nps") == "Detractor" and pain_point(row):
        return "Alta"
    if row.get("tipo_nps") == "Detractor":
        return "Media"
    if row.get("tipo_nps") == "Pasivo":
        return "Media"
    return "Baja"


def render_kpi_cards(df: pd.DataFrame, full_df: pd.DataFrame) -> None:
    unique = filtered_unique_surveys(df)
    previous_delta = ""
    if "mes" in df.columns and not full_df.empty:
        months = sorted([m for m in full_df["mes"].dropna().unique() if m != "Sin fecha"])
        current_month = df["mes"].mode().iloc[0] if not df.empty and not df["mes"].empty else None
        if current_month in months:
            idx = months.index(current_month)
            if idx > 0:
                prev_df = full_df[full_df["mes"] == months[idx - 1]]
                previous_delta = f"{nps_score(df) - nps_score(prev_df):+.1f} vs mes ant."

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    total = len(unique)
    promoters = int(unique["tipo_nps"].eq("Promotor").sum()) if not unique.empty else 0
    passive = int(unique["tipo_nps"].eq("Pasivo").sum()) if not unique.empty else 0
    detractors = int(unique["tipo_nps"].eq("Detractor").sum()) if not unique.empty else 0
    k1.metric("NPS", f"{nps_score(unique):.1f}", previous_delta)
    k2.metric("Encuestas", f"{total:,.0f}".replace(",", "."))
    k3.metric("Promotores", f"{promoters:,.0f}".replace(",", "."), f"{pct_value(promoters, total):.1f}%")
    k4.metric("Pasivos", f"{passive:,.0f}".replace(",", "."), f"{pct_value(passive, total):.1f}%")
    k5.metric("Detractores", f"{detractors:,.0f}".replace(",", "."), f"{pct_value(detractors, total):.1f}%")
    k6.metric("Planes guardados", f"{len(load_shared_plans()):,.0f}".replace(",", "."))


def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for mes, group in df[df["mes"] != "Sin fecha"].groupby("mes"):
        unique = filtered_unique_surveys(group)
        total = len(unique)
        promoters = int(unique["tipo_nps"].eq("Promotor").sum())
        passive = int(unique["tipo_nps"].eq("Pasivo").sum())
        detractors = int(unique["tipo_nps"].eq("Detractor").sum())
        rows.append(
            {
                "mes": mes,
                "NPS": nps_score(unique),
                "Encuestas": total,
                "Promotores": promoters,
                "Pasivos": passive,
                "Detractores": detractors,
                "% Promotores": pct_value(promoters, total),
                "% Pasivos": pct_value(passive, total),
                "% Detractores": pct_value(detractors, total),
            }
        )
    return pd.DataFrame(rows).sort_values("mes")


def promoter_ranking(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for promotor, group in df.groupby("promotor", dropna=False):
        unique = filtered_unique_surveys(group)
        if unique.empty:
            continue
        rows.append(
            {
                "Promotor": promotor,
                "NPS": nps_score(unique),
                "Encuestas": len(unique),
                "Detractores": int(unique["tipo_nps"].eq("Detractor").sum()),
                "Pasivos": int(unique["tipo_nps"].eq("Pasivo").sum()),
                "Promotores": int(unique["tipo_nps"].eq("Promotor").sum()),
            }
        )
    return pd.DataFrame(rows).sort_values(["NPS", "Encuestas"], ascending=[False, False])


def recurrent_clients(df: pd.DataFrame) -> pd.DataFrame:
    scoped = df[df["tipo_nps"].isin(["Detractor", "Pasivo"])].copy()
    if scoped.empty:
        return pd.DataFrame()
    return (
        scoped.groupby(["cliente_codigo", "cliente"], as_index=False)
        .agg(
            meses=("mes", "nunique"),
            casos=("id", "count"),
            ultimo_mes=("mes", "max"),
            ultimo_score=("score", "last"),
            driver=("driver", "last"),
            subdriver=("subdriver", "last"),
            promotor=("promotor", "last"),
        )
        .sort_values(["meses", "casos"], ascending=False)
    )


def plan_api_url() -> str:
    return secret_or_env("PLANES_ACCION_NPS_API_URL", DEFAULT_PLAN_API_URL)


@st.cache_data(ttl=30, show_spinner=False)
def load_shared_plans() -> pd.DataFrame:
    url = plan_api_url()
    if not url:
        return pd.DataFrame()
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame(data)


def save_shared_plan(plan: dict[str, object]) -> bool:
    url = plan_api_url()
    if not url:
        return False
    payload = {k: "" if pd.isna(v) else v for k, v in plan.items()}
    try:
        response = requests.post(url, json=payload, timeout=20)
        response.raise_for_status()
        st.cache_data.clear()
        return True
    except Exception as exc:
        st.error(f"No pude guardar el plan compartido: {exc}")
        return False


def css() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #0f172a; color: #f8fafc; }
        .block-container { padding-top: 1.2rem; }
        [data-testid="stSidebar"] { background: #111827; border-right: 1px solid rgba(148,163,184,.25); }
        .hero { padding: 24px; border-radius: 16px; background: linear-gradient(120deg,#7c3aed,#2563eb 45%,#06b6d4); box-shadow: 0 20px 50px rgba(0,0,0,.25); margin-bottom: 18px; }
        .hero h1 { margin: 0; font-size: 38px; color: #fff; }
        .hero p { margin: 6px 0 0; color: rgba(255,255,255,.82); }
        .card { background: #111827; border: 1px solid rgba(148,163,184,.22); border-radius: 14px; padding: 16px; box-shadow: 0 16px 36px rgba(0,0,0,.2); }
        .metric { font-size: 32px; font-weight: 900; color: #fff; }
        .label { color: #cbd5e1; font-size: 13px; }
        .footer { color: #94a3b8; font-size: 12px; text-align: right; margin-top: 26px; }
        div[data-testid="stMetric"] { background: #111827; border: 1px solid rgba(148,163,184,.22); border-radius: 14px; padding: 14px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def action_text(row: pd.Series) -> str:
    if row["tipo_nps"] == "Detractor":
        return f"Contactar al cliente por {row['driver']} / {row['subdriver']}, registrar causa raiz y cerrar accion correctiva."
    if row["tipo_nps"] == "Pasivo":
        return f"Convertir experiencia pasiva en promotor: seguimiento comercial sobre {row['driver']} y mejora puntual."
    return "Sostener experiencia positiva y detectar oportunidad de recomendacion o crecimiento."


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="📈", layout="wide")
    css()
    st.markdown(
        "<div class='hero'><h1>NPS Galaxia</h1><p>Net Promoter Score con planes de accion compartidos</p></div>",
        unsafe_allow_html=True,
    )

    if st.sidebar.button("Actualizar datos"):
        st.cache_data.clear()
        st.rerun()

    refresh_key = secret_or_env("FORCE_GDRIVE_REFRESH", "false")
    df, meta = load_nps_data(refresh_key)
    if df.empty:
        st.error(meta.get("error", "No hay datos NPS disponibles."))
        st.stop()

    months = sorted([m for m in df["mes"].dropna().unique() if m != "Sin fecha"])
    selected_month = st.sidebar.selectbox("Mes", ["Todos", *months], index=len(months) if months else 0)
    promotor = st.sidebar.selectbox("Promotor", ["Todos", *sorted(df["promotor"].dropna().unique())])
    tipo = st.sidebar.selectbox("Tipo NPS", ["Todos", "Detractor", "Pasivo", "Promotor"])
    driver = st.sidebar.selectbox("Driver", ["Todos", *sorted(df["driver"].dropna().unique())])

    filtered = df.copy()
    if selected_month != "Todos":
        filtered = filtered[filtered["mes"] == selected_month]
    if promotor != "Todos":
        filtered = filtered[filtered["promotor"] == promotor]
    if tipo != "Todos":
        filtered = filtered[filtered["tipo_nps"] == tipo]
    if driver != "Todos":
        filtered = filtered[filtered["driver"] == driver]

    render_kpi_cards(filtered, df)

    tab_resumen, tab_drivers, tab_dolor, tab_sugeridos, tab_planes, tab_promotores, tab_auditoria = st.tabs(
        [
            "Resumen ejecutivo",
            "Driver y Subdriver",
            "Puntos de dolor",
            "Planes sugeridos",
            "Plan mensual compartido",
            "Promotores / Rutas",
            "Auditoria Galaxia",
        ]
    )

    with tab_resumen:
        left, right = st.columns((1.2, 1))
        monthly = monthly_summary(df)
        left.plotly_chart(
            px.line(monthly, x="mes", y="NPS", markers=True, title="Evolucion mensual NPS"),
            use_container_width=True,
        )
        mix = filtered_unique_surveys(filtered)["tipo_nps"].value_counts().reset_index()
        mix.columns = ["Tipo", "Encuestas"]
        right.plotly_chart(
            px.pie(
                mix,
                names="Tipo",
                values="Encuestas",
                hole=.55,
                title="Composicion NPS",
                color="Tipo",
                color_discrete_map={"Promotor": "#22c55e", "Pasivo": "#facc15", "Detractor": "#fb7185"},
            ),
            use_container_width=True,
        )
        st.subheader("Resumen mensual")
        st.dataframe(
            monthly.style.format(
                {
                    "NPS": "{:.1f}",
                    "% Promotores": "{:.1f}%",
                    "% Pasivos": "{:.1f}%",
                    "% Detractores": "{:.1f}%",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.subheader("Base filtrada")
        st.dataframe(
            filtered[["mes", "cliente_codigo", "cliente", "score", "tipo_nps", "driver", "subdriver", "promotor", "comentario"]],
            use_container_width=True,
            hide_index=True,
        )

    with tab_drivers:
        detractors = filtered[filtered["tipo_nps"].isin(["Detractor", "Pasivo"])]
        driver_summary = detractors.groupby(["driver", "subdriver"], as_index=False).size().rename(columns={"size": "casos"})
        driver_totals = detractors.groupby("driver", as_index=False).size().rename(columns={"size": "casos"})
        c1, c2 = st.columns((1, 1))
        c1.plotly_chart(
            px.treemap(driver_summary, path=["driver", "subdriver"], values="casos", color="casos", title="Arbol de drivers y subdrivers"),
            use_container_width=True,
        )
        c2.plotly_chart(
            px.bar(driver_totals.sort_values("casos", ascending=False), x="driver", y="casos", color="driver", title="Casos por driver"),
            use_container_width=True,
        )
        st.plotly_chart(
            px.bar(driver_summary.sort_values("casos", ascending=False).head(20), x="casos", y="subdriver", color="driver", orientation="h", title="Principales drivers de dolor"),
            use_container_width=True,
        )
        st.dataframe(driver_summary.sort_values("casos", ascending=False), use_container_width=True, hide_index=True)

    with tab_dolor:
        pain = filtered.copy()
        pain["punto_de_dolor"] = pain.apply(pain_point, axis=1)
        pain = pain[pain["punto_de_dolor"] | pain["tipo_nps"].isin(["Detractor", "Pasivo"])]
        c1, c2, c3 = st.columns(3)
        c1.metric("Casos a revisar", len(pain))
        c2.metric("Clientes afectados", pain["cliente_codigo"].nunique())
        c3.metric("Drivers distintos", pain["driver"].nunique())
        if not pain.empty:
            st.plotly_chart(
                px.scatter(
                    pain,
                    x="score",
                    y="driver",
                    color="tipo_nps",
                    size=[1] * len(pain),
                    hover_data=["cliente", "subdriver", "comentario", "promotor"],
                    title="Mapa de puntos de dolor por score y driver",
                    color_discrete_map={"Promotor": "#22c55e", "Pasivo": "#facc15", "Detractor": "#fb7185"},
                ),
                use_container_width=True,
            )
        st.dataframe(
            pain[["mes", "cliente_codigo", "cliente", "score", "tipo_nps", "driver", "subdriver", "promotor", "comentario"]],
            use_container_width=True,
            hide_index=True,
        )

    with tab_sugeridos:
        plan_candidates = filtered[filtered["tipo_nps"].isin(["Detractor", "Pasivo"])].copy()
        if plan_candidates.empty:
            st.info("No hay detractores o pasivos con los filtros actuales.")
        else:
            plan_candidates["prioridad"] = plan_candidates.apply(priority_for, axis=1)
            plan_candidates["problema"] = plan_candidates.apply(
                lambda r: f"{r['tipo_nps']} por {r['driver']} / {r['subdriver']}",
                axis=1,
            )
            plan_candidates["accion_recomendada"] = plan_candidates.apply(action_text, axis=1)
            plan_candidates["responsable_sugerido"] = plan_candidates["promotor"]
            plan_candidates["estado_sugerido"] = "Pendiente"
            st.plotly_chart(
                px.bar(
                    plan_candidates.groupby(["prioridad", "driver"], as_index=False).size().rename(columns={"size": "casos"}),
                    x="driver",
                    y="casos",
                    color="prioridad",
                    title="Planes sugeridos por prioridad",
                    color_discrete_map={"Alta": "#fb7185", "Media": "#facc15", "Baja": "#22c55e"},
                ),
                use_container_width=True,
            )
            st.dataframe(
                plan_candidates[
                    [
                        "mes",
                        "cliente_codigo",
                        "cliente",
                        "score",
                        "tipo_nps",
                        "driver",
                        "subdriver",
                        "problema",
                        "accion_recomendada",
                        "responsable_sugerido",
                        "prioridad",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

    with tab_planes:
        plans = load_shared_plans()
        if plan_api_url() and plans.empty:
            st.caption(
                "Si ya existen planes y no aparecen, revisar que el Apps Script este publicado para 'Cualquier persona'."
            )
        candidates = filtered[filtered["tipo_nps"].isin(["Detractor", "Pasivo"])].copy()
        if candidates.empty:
            st.info("No hay detractores o pasivos con los filtros actuales.")
        else:
            candidates["label"] = candidates.apply(
                lambda r: f"{r['mes']} | {r['cliente_codigo']} | {r['cliente']} | {r['tipo_nps']} | {r['driver']}",
                axis=1,
            )
            selected_label = st.selectbox("Cliente para plan de accion", candidates["label"].tolist())
            selected = candidates[candidates["label"] == selected_label].iloc[0]
            plan_id = f"{selected['mes']}|{selected['cliente_codigo']}|{selected['driver']}|{selected['subdriver']}"
            existing = plans[plans.get("id_plan", pd.Series(dtype=str)).astype(str).eq(plan_id)] if not plans.empty else pd.DataFrame()
            existing_row = existing.iloc[0].to_dict() if not existing.empty else {}

            with st.form("plan_form"):
                c1, c2, c3 = st.columns(3)
                prioridad = c1.selectbox("Prioridad", ["Alta", "Media", "Baja"], index=["Alta", "Media", "Baja"].index(existing_row.get("prioridad", "Alta")) if existing_row.get("prioridad") in ["Alta", "Media", "Baja"] else 0)
                estado = c2.selectbox("Estado", ["Pendiente", "En curso", "Cerrado"], index=["Pendiente", "En curso", "Cerrado"].index(existing_row.get("estado", "Pendiente")) if existing_row.get("estado") in ["Pendiente", "En curso", "Cerrado"] else 0)
                responsable = c3.text_input("Responsable", value=str(existing_row.get("responsable", selected["promotor"]) or ""))
                problema = st.text_area("Problema detectado", value=str(existing_row.get("problema", f"{selected['tipo_nps']} por {selected['driver']} / {selected['subdriver']}") or ""))
                accion = st.text_area("Accion recomendada", value=str(existing_row.get("accion_recomendada", action_text(selected)) or ""))
                realizada = st.text_area("Accion realizada", value=str(existing_row.get("accion_realizada", "") or ""))
                comentario = st.text_area("Comentario", value=str(existing_row.get("comentario", selected["comentario"]) or ""))
                fecha_accion = st.date_input("Fecha accion", value=pd.Timestamp.today().date())
                submitted = st.form_submit_button("Guardar plan compartido")

            if submitted:
                plan = {
                    "id_plan": plan_id,
                    "mes": selected["mes"],
                    "cliente_codigo": selected["cliente_codigo"],
                    "cliente": selected["cliente"],
                    "tipo_nps": selected["tipo_nps"],
                    "score": selected["score"],
                    "driver": selected["driver"],
                    "subdriver": selected["subdriver"],
                    "problema": problema,
                    "accion_recomendada": accion,
                    "accion_realizada": realizada,
                    "responsable": responsable,
                    "prioridad": prioridad,
                    "estado": estado,
                    "comentario": comentario,
                    "fecha_accion": str(fecha_accion),
                    "fecha_actualizacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                if save_shared_plan(plan):
                    st.success("Plan guardado en Google Sheet para todos los usuarios.")
                    st.rerun()

        st.subheader("Planes guardados")
        if plans.empty:
            st.info("Todavia no hay planes guardados en el Sheet.")
        else:
            st.dataframe(plans, use_container_width=True, hide_index=True)

    with tab_promotores:
        ranking = promoter_ranking(filtered)
        c1, c2 = st.columns((1.2, 1))
        if not ranking.empty:
            c1.plotly_chart(
                px.bar(
                    ranking.sort_values("NPS").tail(15),
                    x="NPS",
                    y="Promotor",
                    color="NPS",
                    orientation="h",
                    title="Ranking de promotores por NPS",
                    color_continuous_scale=["#fb7185", "#facc15", "#22c55e"],
                ),
                use_container_width=True,
            )
            c2.plotly_chart(
                px.bar(
                    ranking.sort_values("Detractores", ascending=False).head(15),
                    x="Detractores",
                    y="Promotor",
                    orientation="h",
                    title="Promotores con mas detractores",
                    color="Detractores",
                    color_continuous_scale=["#22c55e", "#facc15", "#fb7185"],
                ),
                use_container_width=True,
            )
        st.dataframe(ranking, use_container_width=True, hide_index=True)
        st.subheader("Clientes recurrentes detractores/pasivos")
        st.dataframe(recurrent_clients(df), use_container_width=True, hide_index=True)

    with tab_auditoria:
        st.write("Fuente de datos")
        st.json(meta)
        st.write("Calidad de cruces")
        st.dataframe(
            pd.DataFrame(
                [
                    {"Indicador": "Encuestas normalizadas", "Valor": len(df)},
                    {"Indicador": "Clientes cruzados", "Valor": int(df["matched_client"].sum())},
                    {"Indicador": "Rutas/promotores cruzados", "Valor": int(df["matched_route"].sum())},
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        requirements = pd.DataFrame(
            [
                {"Requisito": "Archivo NPS", "Estado": "OK" if meta.get("nps_file") != "No detectado" else "FALTA", "Detalle": meta.get("nps_file")},
                {"Requisito": "Score", "Estado": "OK" if "score" in df.columns else "FALTA", "Detalle": "Columna normalizada score"},
                {"Requisito": "Fecha encuesta", "Estado": "OK" if "fecha" in df.columns else "FALTA", "Detalle": "Fecha normalizada"},
                {"Requisito": "Drivers/Subdrivers", "Estado": "OK" if {"driver", "subdriver"}.issubset(df.columns) else "FALTA", "Detalle": "Driver y subdriver normalizados"},
                {"Requisito": "Promotor/Ruta", "Estado": "PARCIAL" if int(df["matched_route"].sum()) < len(df) else "OK", "Detalle": f"{int(df['matched_route'].sum())}/{len(df)} encuestas con ruta/promotor"},
                {"Requisito": "Planes compartidos", "Estado": "OK" if plan_api_url() else "FALTA", "Detalle": "Google Sheet via Apps Script"},
            ]
        )
        st.subheader("Estado Galaxia")
        ok_count = int(requirements["Estado"].eq("OK").sum())
        st.progress(ok_count / len(requirements))
        st.dataframe(requirements, use_container_width=True, hide_index=True)

    st.markdown("<div class='footer'>by QπU</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
