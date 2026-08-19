"""
Nutri & Drink Calculator
=========================
Streamlit app derived from "NUTRI AND DRINK CALCULATOR v3.0" (Excel).

Working areas:
- Inventario: list of food/nutrition items (PRODOTTO, MARCA, g CARBO,
  SODIO [mg], CALORIE [kcal] — values are "per unit"), managed with plain
  st.text_input / st.number_input widgets (no editable table/grid).
- Piano gara: optional detailed race plan split into consecutive sections
  (Nome sezione + Durata sezione, hh:mm), whose durations must sum exactly
  to the total race time.
- Calcoli: pick items from the inventario, set how many units of each you
  plan to use during the race plus optional liquid (ml) per unit; the app
  computes total carbs, liquid, sodium and calories, the hourly rates, and
  compares them against configurable min/max targets — overall and, if a
  race plan is active, broken down per section.
"""

import os
import re

import pandas as pd
import streamlit as st

MAX_DURATION_HOURS = 99

st.set_page_config(page_title="DU Nutri & Drink Calculator", page_icon="🥤", layout="wide")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
INVENTARIO_PATH = os.path.join(APP_DIR, "inventario.csv")

INVENTARIO_COLS = ["PRODOTTO", "MARCA", "g CARBO", "SODIO [mg]", "CALORIE [kcal]"]

DEFAULT_TARGETS = {
    "min": {"LIQUIDO [ml/h]": 475.0, "CARBO [g/h]": 30.0, "SODIO [mg/l]": 600.0, "CALORIE [kcal/h]": 120.0},
    "max": {"LIQUIDO [ml/h]": 950.0, "CARBO [g/h]": 90.0, "SODIO [mg/l]": 800.0, "CALORIE [kcal/h]": 360.0},
}


# ----------------------------------------------------------------------------
# Data loading / persistence
# ----------------------------------------------------------------------------
def load_inventario_rows() -> list:
    """Read inventario.csv and return a list of row-dicts with stable ids."""
    rows = []
    if os.path.exists(INVENTARIO_PATH):
        df = pd.read_csv(INVENTARIO_PATH)
        for col in INVENTARIO_COLS:
            if col not in df.columns:
                df[col] = "" if col in ("PRODOTTO", "MARCA") else 0.0
        for i, r in df.iterrows():
            rows.append(
                {
                    "id": i,
                    "PRODOTTO": "" if pd.isna(r["PRODOTTO"]) else str(r["PRODOTTO"]),
                    "MARCA": "" if pd.isna(r["MARCA"]) else str(r["MARCA"]),
                    "g CARBO": float(r["g CARBO"]) if pd.notna(r["g CARBO"]) else 0.0,
                    "SODIO [mg]": float(r["SODIO [mg]"]) if pd.notna(r["SODIO [mg]"]) else 0.0,
                    "CALORIE [kcal]": float(r["CALORIE [kcal]"]) if pd.notna(r["CALORIE [kcal]"]) else 0.0,
                }
            )
    return rows


def rows_to_df(rows: list) -> pd.DataFrame:
    clean = [r for r in rows if str(r.get("PRODOTTO", "")).strip() != ""]
    return pd.DataFrame(
        [
            {
                "PRODOTTO": r["PRODOTTO"].strip(),
                "MARCA": r["MARCA"].strip(),
                "g CARBO": r["g CARBO"],
                "SODIO [mg]": r["SODIO [mg]"],
                "CALORIE [kcal]": r["CALORIE [kcal]"],
            }
            for r in clean
        ],
        columns=INVENTARIO_COLS,
    )


def save_inventario_rows(rows: list) -> None:
    rows_to_df(rows).to_csv(INVENTARIO_PATH, index=False)


def df_to_rows(df: pd.DataFrame) -> list:
    rows = []
    for col in INVENTARIO_COLS:
        if col not in df.columns:
            df[col] = "" if col in ("PRODOTTO", "MARCA") else 0.0
    for i, r in df.iterrows():
        rows.append(
            {
                "id": i,
                "PRODOTTO": "" if pd.isna(r["PRODOTTO"]) else str(r["PRODOTTO"]),
                "MARCA": "" if pd.isna(r["MARCA"]) else str(r["MARCA"]),
                "g CARBO": float(r["g CARBO"]) if pd.notna(r["g CARBO"]) else 0.0,
                "SODIO [mg]": float(r["SODIO [mg]"]) if pd.notna(r["SODIO [mg]"]) else 0.0,
                "CALORIE [kcal]": float(r["CALORIE [kcal]"]) if pd.notna(r["CALORIE [kcal]"]) else 0.0,
            }
        )
    return rows


def next_id(rows: list) -> int:
    return (max((r["id"] for r in rows), default=-1)) + 1


# ----------------------------------------------------------------------------
# Piano gara helpers
# ----------------------------------------------------------------------------
def minutes_to_hhmm(m: int) -> str:
    m = int(round(m))
    sign = "-" if m < 0 else ""
    m = abs(m)
    h, mm = divmod(m, 60)
    return f"{sign}{h}:{mm:02d}"


HHMM_RE = re.compile(r"^\s*(\d{1,3}):([0-5]?\d)\s*$")


def hhmm_input(label: str, total_minutes: int, key: str, container=None, max_hours: int = MAX_DURATION_HOURS) -> int:
    """Render a single HH:MM text box for a duration / time-of-day value (supports up to
    `max_hours` hours) and return the value as total minutes. Validates the format inline
    and falls back to the last valid value if what's typed doesn't match HH:MM."""
    container = container if container is not None else st
    total_minutes = int(total_minutes) if total_minutes else 0
    total_minutes = max(0, min(total_minutes, max_hours * 60 + 59))
    default_str = minutes_to_hhmm(total_minutes)
    text = container.text_input(f"{label} (HH:MM)", value=default_str, key=key)
    text = str(text) if text is not None else ""
    match = HHMM_RE.match(text)
    if not match:
        container.caption("⚠️ Formato non valido: usa HH:MM (es. 4:30).")
        return total_minutes
    hh = min(int(match.group(1)), max_hours)
    mm = int(match.group(2))
    return hh * 60 + mm


def section_boundaries(sections: list) -> list:
    """Return sections with cumulative start/end (in minutes), in insertion order."""
    bounds = []
    cursor = 0
    for s in sections:
        dur = int(s["durata"])
        start = cursor
        end = cursor + dur
        bounds.append({"id": s["id"], "nome": s["nome"], "start": start, "end": end, "durata_min": dur})
        cursor = end
    return bounds


def hourly_buckets(total_minutes: int) -> list:
    """Split [0, total_minutes] into whole-hour buckets, with a final partial bucket if needed."""
    buckets = []
    full_hours = int(total_minutes // 60)
    for h in range(full_hours):
        start, end = h * 60, (h + 1) * 60
        buckets.append({"start": start, "end": end, "durata_min": end - start})
    rem = total_minutes - full_hours * 60
    if rem > 0:
        start = full_hours * 60
        buckets.append({"start": start, "end": total_minutes, "durata_min": rem})
    return buckets


# ----------------------------------------------------------------------------
# Session state init
# ----------------------------------------------------------------------------
if "inventario_rows" not in st.session_state:
    st.session_state.inventario_rows = load_inventario_rows()

if "race_rows" not in st.session_state:
    st.session_state.race_rows = [
        {
            "id": 0,
            "PRODOTTO": None,
            "n": 1.0,
            "LIQUIDO [ml/unita]": 0.0,
            "note": "",
            "SEZIONE": None,
            "ORARIO": 0,
        }
    ]
    st.session_state.race_next_id = 1

if "time_dist_enabled" not in st.session_state:
    st.session_state.time_dist_enabled = False

if "targets" not in st.session_state:
    st.session_state.targets = {k: dict(v) for k, v in DEFAULT_TARGETS.items()}

if "race_hours" not in st.session_state:
    st.session_state.race_hours = 4.0

if "plan_enabled" not in st.session_state:
    st.session_state.plan_enabled = False

if "plan_total_time" not in st.session_state:
    st.session_state.plan_total_time = 4 * 60

if "plan_sections" not in st.session_state:
    st.session_state.plan_sections = []
    st.session_state.plan_next_id = 0


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
logo_path = os.path.join(APP_DIR, "assets", "logo_tondo_du.jpg")
wordmark_path = os.path.join(APP_DIR, "assets", "SCRITTA_ULTRANERD.png")

header_logo, header_word = st.columns([1, 4])
with header_logo:
    if os.path.exists(logo_path):
        st.image(logo_path, width=90)
with header_word:
    if os.path.exists(wordmark_path):
        st.image(wordmark_path, width=260)

st.title("🥤 DU Nutri & Drink Calculator")
st.caption("Basato su NUTRI AND DRINK CALCULATOR v3.0 — tab Inventario, Piano gara e Calcoli")
st.markdown(
    """
    <div style="
        background-color:#FFDD57;
        border-radius:10px;
        padding:12px 18px;
        margin:8px 0 16px 0;
        font-size:1.05rem;
        color:#3d2b00;
    ">
        Questa app è stata creata da <strong>Ultranerd</strong> per <strong>Destination Unknown</strong>.
        L'app è gratuita, ma se vuoi
        <a href="https://buymeacoffee.com/ultranerd" target="_blank" style="color:#3d2b00; font-weight:700; text-decoration:underline;">
            puoi cliccare qui e offrirmi un caffè
        </a>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_inv, tab_plan, tab_race = st.tabs(["📦 Inventario", "🗺️ Piano gara", "🏃 Calcoli"])

# ---------------------------------------------------------------- Inventario
with tab_inv:
    st.subheader("Inventario prodotti")
    st.caption("Valori **per unità/porzione**. Ogni riga ha i propri campi: modifica, poi salva.")

    rows_to_remove = []
    for row in st.session_state.inventario_rows:
        rid = row["id"]
        with st.container(border=True):
            c1, c2, c3, c4, c5, c6 = st.columns([2.2, 1.6, 1.2, 1.2, 1.2, 0.6])
            row["PRODOTTO"] = c1.text_input("PRODOTTO", value=row["PRODOTTO"], key=f"inv_prodotto_{rid}")
            row["MARCA"] = c2.text_input("MARCA", value=row["MARCA"], key=f"inv_marca_{rid}")
            row["g CARBO"] = c3.number_input(
                "g CARBO", value=float(row["g CARBO"]), min_value=0.0, step=0.1, format="%.2f", key=f"inv_carbo_{rid}"
            )
            row["SODIO [mg]"] = c4.number_input(
                "SODIO [mg]", value=float(row["SODIO [mg]"]), min_value=0.0, step=1.0, format="%.1f", key=f"inv_sodio_{rid}"
            )
            row["CALORIE [kcal]"] = c5.number_input(
                "CALORIE [kcal]", value=float(row["CALORIE [kcal]"]), min_value=0.0, step=1.0, format="%.1f", key=f"inv_cal_{rid}"
            )
            c6.write("")
            if c6.button("🗑️", key=f"inv_del_{rid}", help="Rimuovi prodotto"):
                rows_to_remove.append(rid)

    if rows_to_remove:
        st.session_state.inventario_rows = [r for r in st.session_state.inventario_rows if r["id"] not in rows_to_remove]
        st.rerun()

    st.markdown("**➕ Aggiungi nuovo prodotto**")
    with st.form("add_inventario_form", clear_on_submit=True):
        a1, a2, a3, a4, a5 = st.columns([2.2, 1.6, 1.2, 1.2, 1.2])
        new_prodotto = a1.text_input("PRODOTTO")
        new_marca = a2.text_input("MARCA")
        new_carbo = a3.number_input("g CARBO", min_value=0.0, step=0.1, format="%.2f")
        new_sodio = a4.number_input("SODIO [mg]", min_value=0.0, step=1.0, format="%.1f")
        new_calorie = a5.number_input("CALORIE [kcal]", min_value=0.0, step=1.0, format="%.1f")
        submitted = st.form_submit_button("Aggiungi")
        if submitted:
            if new_prodotto.strip() == "":
                st.warning("Inserisci un nome per il PRODOTTO.")
            else:
                st.session_state.inventario_rows.append(
                    {
                        "id": next_id(st.session_state.inventario_rows),
                        "PRODOTTO": new_prodotto,
                        "MARCA": new_marca,
                        "g CARBO": new_carbo,
                        "SODIO [mg]": new_sodio,
                        "CALORIE [kcal]": new_calorie,
                    }
                )
                st.rerun()

    st.divider()
    with st.container(border=True):
        st.markdown("**💾 Salva / ripristina**")
        col_a, col_b = st.columns(2, gap="large")
        with col_a:
            st.caption("Salva le modifiche fatte sopra su inventario.csv.")
            if st.button("Salva inventario", type="primary", use_container_width=True):
                save_inventario_rows(st.session_state.inventario_rows)
                st.success("Inventario salvato.")
        with col_b:
            st.caption("Annulla le modifiche non salvate e ricarica da inventario.csv.")
            if st.button("Ripristina da file", use_container_width=True):
                st.session_state.inventario_rows = load_inventario_rows()
                st.rerun()

    st.divider()
    with st.container(border=True):
        st.markdown("**⇅ Esporta / importa inventario**")
        col_dl, col_up = st.columns(2, gap="large")

        with col_dl:
            st.caption("Scarica l'inventario attuale")
            csv_bytes = rows_to_df(st.session_state.inventario_rows).to_csv(index=False).encode("utf-8")
            st.download_button(
                "Scarica CSV",
                data=csv_bytes,
                file_name="inventario_du_nutridrinkcalculator.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with col_up:
            st.caption("Carica un inventario precedentemente scaricato")
            uploaded_csv = st.file_uploader(
                "Carica CSV",
                type=["csv"],
                key="inventario_uploader",
                label_visibility="collapsed",
            )
            if uploaded_csv is not None:
                try:
                    uploaded_df = pd.read_csv(uploaded_csv)
                    if "PRODOTTO" not in uploaded_df.columns:
                        st.error("Il CSV non contiene la colonna 'PRODOTTO'. Verifica il file e riprova.")
                    else:
                        if st.button("Sostituisci inventario", type="primary", use_container_width=True):
                            st.session_state.inventario_rows = df_to_rows(uploaded_df)
                            save_inventario_rows(st.session_state.inventario_rows)
                            st.success("Inventario importato e salvato.")
                            st.rerun()
                except Exception as e:
                    st.error(f"Errore nella lettura del CSV: {e}")

# ---------------------------------------------------------------- Piano gara
with tab_plan:
    st.subheader("Piano gara")

    st.session_state.plan_enabled = st.checkbox(
        "Vuoi creare un piano gara dettagliato?",
        value=st.session_state.plan_enabled,
    )

    if not st.session_state.plan_enabled:
        st.info(
            "Attiva la casella per dividere la gara in sezioni consecutive (es. Salita, Discesa, "
            "Ristoro...) e calcolare carbo/liquido/sodio/calorie anche per singola sezione, oltre "
            "che sul totale."
        )
    else:
        st.session_state.plan_total_time = hhmm_input(
            "⏱️ Tempo totale gara",
            st.session_state.plan_total_time,
            key="plan_total_time_hhmm",
        )
        total_min = st.session_state.plan_total_time

        st.markdown("**Sezioni**")
        st.caption(
            "Le sezioni sono consecutive: l'inizio di ciascuna coincide automaticamente con la fine "
            "della precedente. La somma delle durate deve essere uguale al tempo totale."
        )

        sections_to_remove = []
        bounds = section_boundaries(st.session_state.plan_sections)
        for sec, b in zip(st.session_state.plan_sections, bounds):
            sid = sec["id"]
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2.4, 1.4, 1.8, 0.6])
                sec["nome"] = c1.text_input("Nome sezione", value=sec["nome"], key=f"plan_nome_{sid}")
                sec["durata"] = hhmm_input(
                    "Durata sezione", sec["durata"], key=f"plan_durata_hhmm_{sid}", container=c2
                )
                c3.markdown(f"**{minutes_to_hhmm(b['start'])} → {minutes_to_hhmm(b['start'] + sec['durata'])}**")
                c3.caption("inizio → fine (calcolato)")
                c4.write("")
                if c4.button("🗑️", key=f"plan_del_{sid}", help="Rimuovi sezione"):
                    sections_to_remove.append(sid)

        if sections_to_remove:
            st.session_state.plan_sections = [s for s in st.session_state.plan_sections if s["id"] not in sections_to_remove]
            st.rerun()

        # recompute after possible edits above (values already mutated in place)
        bounds = section_boundaries(st.session_state.plan_sections)
        assigned_min = bounds[-1]["end"] if bounds else 0
        remaining_min = total_min - assigned_min

        if st.button("➕ Aggiungi sezione"):
            default_dur_min = max(remaining_min, 0)
            st.session_state.plan_sections.append(
                {
                    "id": st.session_state.plan_next_id,
                    "nome": f"Sezione {len(st.session_state.plan_sections) + 1}",
                    "durata": default_dur_min,
                }
            )
            st.session_state.plan_next_id += 1
            st.rerun()

        st.divider()
        if not st.session_state.plan_sections:
            st.info("Aggiungi almeno una sezione per costruire il piano gara.")
        elif assigned_min == total_min and total_min > 0:
            st.success(
                f"Piano completo: le sezioni coprono {minutes_to_hhmm(assigned_min)} su "
                f"{minutes_to_hhmm(total_min)} totali. ✅ Ora puoi assegnare una sezione a ogni "
                f"prodotto nel tab Calcoli."
            )
        elif assigned_min < total_min:
            st.warning(
                f"Mancano {minutes_to_hhmm(remaining_min)} per coprire il tempo totale "
                f"({minutes_to_hhmm(assigned_min)} su {minutes_to_hhmm(total_min)})."
            )
        else:
            st.error(
                f"Le sezioni superano il tempo totale di {minutes_to_hhmm(-remaining_min)} "
                f"({minutes_to_hhmm(assigned_min)} su {minutes_to_hhmm(total_min)})."
            )

# -------------------------------------------------------------------- Calcoli
with tab_race:
    st.subheader("Calcoli")

    st.session_state.time_dist_enabled = st.checkbox(
        "Vuoi analizzare la distribuzione nel tempo?",
        value=st.session_state.time_dist_enabled,
        help=(
            "Se attivo, per ogni prodotto indichi anche il tempo (HH:MM) trascorso dall'inizio — se "
            "il piano gara è attivo, dall'inizio della sezione a cui appartiene, altrimenti dalla "
            "partenza: nel tab 'Distribuzione oraria' trovi il confronto ora per ora con i tassi "
            "orari consigliati."
        ),
    )

    inv_df = pd.DataFrame(
        [r for r in st.session_state.inventario_rows if str(r["PRODOTTO"]).strip() != ""]
    )
    if inv_df.empty:
        inv_lookup = pd.DataFrame(columns=["g CARBO", "SODIO [mg]", "CALORIE [kcal]"])
        item_options = []
    else:
        inv_lookup = inv_df.set_index("PRODOTTO")[["g CARBO", "SODIO [mg]", "CALORIE [kcal]"]]
        item_options = sorted(inv_df["PRODOTTO"].unique().tolist())

    # ---- determine whether the race plan is usable here ----
    plan_bounds = []
    plan_active = False
    if st.session_state.plan_enabled and st.session_state.plan_sections:
        plan_bounds = section_boundaries(st.session_state.plan_sections)
        plan_total_min = st.session_state.plan_total_time
        plan_assigned_min = plan_bounds[-1]["end"] if plan_bounds else 0
        plan_active = plan_total_min > 0 and plan_assigned_min == plan_total_min
    section_names = [b["nome"] for b in plan_bounds] if plan_active else []

    if not item_options:
        st.warning("L'inventario è vuoto: aggiungi almeno un prodotto nella tab Inventario.")
    else:
        if plan_active:
            hours = st.session_state.plan_total_time / 60.0
            st.info(
                f"🗺️ Piano gara attivo: {len(section_names)} sezioni, durata totale "
                f"{minutes_to_hhmm(st.session_state.plan_total_time)}. La durata gara "
                f"è presa dal Piano gara."
            )
        else:
            race_total_min = hhmm_input(
                "⏱️ Ore corsa (durata gara)",
                int(round(st.session_state.race_hours * 60)),
                key="race_hours_hhmm",
            )
            st.session_state.race_hours = race_total_min / 60.0
            hours = st.session_state.race_hours
            if st.session_state.plan_enabled:
                st.caption(
                    "Il piano gara non è ancora completo (le sezioni non coprono l'intero tempo "
                    "totale): completalo nel tab 'Piano gara' per attivare i calcoli per sezione."
                )

        time_dist = st.session_state.time_dist_enabled
        plan_bounds_by_name = {b["nome"]: b for b in plan_bounds} if plan_active else {}

        if plan_active:
            # keep rows created before the plan existed (or from a deleted section) visible
            # somewhere instead of silently dropping them from every tab
            for r in st.session_state.race_rows:
                if r.get("SEZIONE") not in section_names:
                    r["SEZIONE"] = section_names[0]

        rows_to_remove = []
        rows_to_add = []

        def render_race_row(row, section_name):
            rid = row["id"]
            with st.container(border=True):
                widths = [2.0, 0.9, 1.1]
                if time_dist:
                    widths.append(1.3)
                widths += [1.3, 0.5]
                cols = list(st.columns(widths))

                c1 = cols.pop(0)
                c2 = cols.pop(0)
                c3 = cols.pop(0)
                c_time = cols.pop(0) if time_dist else None
                c4 = cols.pop(0)
                c5 = cols.pop(0)

                current_prodotto = row["PRODOTTO"] if row["PRODOTTO"] in item_options else None
                idx = item_options.index(current_prodotto) if current_prodotto in item_options else 0
                row["PRODOTTO"] = c1.selectbox("PRODOTTO", options=item_options, index=idx, key=f"race_prodotto_{rid}")

                row["n"] = c2.number_input(
                    "n (quantità)", value=float(row["n"]), min_value=0.0, step=1.0, format="%.2f", key=f"race_n_{rid}"
                )
                row["LIQUIDO [ml/unita]"] = c3.number_input(
                    "LIQUIDO [ml/unità]",
                    value=float(row["LIQUIDO [ml/unita]"]),
                    min_value=0.0,
                    step=10.0,
                    format="%.0f",
                    key=f"race_liq_{rid}",
                )

                row["SEZIONE"] = section_name

                if time_dist:
                    current_orario = row.get("ORARIO")
                    if not isinstance(current_orario, (int, float)):
                        current_orario = 0
                    orario_label = "Tempo dall'inizio sezione" if section_name else "Tempo da partenza"
                    row["ORARIO"] = hhmm_input(
                        orario_label, current_orario, key=f"race_orario_{rid}", container=c_time
                    )
                else:
                    row["ORARIO"] = row.get("ORARIO") if isinstance(row.get("ORARIO"), (int, float)) else 0

                if time_dist and section_name and section_name in plan_bounds_by_name:
                    b = plan_bounds_by_name[section_name]
                    orario_rel = int(row["ORARIO"])
                    if not (0 <= orario_rel <= b["durata_min"]):
                        st.warning(
                            f"⚠️ Tempo {minutes_to_hhmm(orario_rel)} fuori dalla durata della sezione "
                            f"**{section_name}** ({minutes_to_hhmm(b['durata_min'])})."
                        )

                row["note"] = c4.text_input("note", value=row["note"], key=f"race_note_{rid}")
                c5.write("")
                if c5.button("🗑️", key=f"race_del_{rid}", help="Rimuovi riga"):
                    rows_to_remove.append(rid)

        target_labels = {
            "LIQUIDO [ml/h]": "Liquido [ml/h]",
            "CARBO [g/h]": "Carbo [g/h]",
            "SODIO [mg/l]": "Sodio [mg/l]",
            "CALORIE [kcal/h]": "Calorie [kcal/h]",
        }

        def render_rate(label, value, unit, target_key):
            tmin = st.session_state.targets["min"][target_key]
            tmax = st.session_state.targets["max"][target_key]
            if value is None:
                st.metric(label, "—")
                st.caption(f"Obiettivo: {tmin:.0f}–{tmax:.0f} {unit}")
                return
            if value < tmin:
                delta_txt, delta_color = "sotto obiettivo", "inverse"
            elif value > tmax:
                delta_txt, delta_color = "sopra obiettivo", "inverse"
            else:
                delta_txt, delta_color = "nel range ✅", "normal"
            st.metric(label, f"{value:.1f} {unit}", delta=delta_txt, delta_color=delta_color)
            st.caption(f"Obiettivo: {tmin:.0f}–{tmax:.0f} {unit}")

        def render_summary(totals_dict, duration_hours):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Liquido totale", f"{totals_dict['LIQUIDO [ml]']:.0f} ml")
            c2.metric("Carboidrati totali", f"{totals_dict['g CARBO']:.1f} g")
            c3.metric("Sodio totale", f"{totals_dict['SODIO [mg]']:.0f} mg")
            c4.metric("Calorie totali", f"{totals_dict['CALORIE [kcal]']:.0f} kcal")

            liquido_h = totals_dict["LIQUIDO [ml]"] / duration_hours if duration_hours > 0 else None
            carbo_h = totals_dict["g CARBO"] / duration_hours if duration_hours > 0 else None
            calorie_h = totals_dict["CALORIE [kcal]"] / duration_hours if duration_hours > 0 else None
            sodio_l = (
                (totals_dict["SODIO [mg]"] / totals_dict["LIQUIDO [ml]"] * 1000)
                if totals_dict["LIQUIDO [ml]"] > 0
                else None
            )

            r1, r2, r3, r4 = st.columns(4)
            with r1:
                render_rate("Liquido", liquido_h, "ml/h", "LIQUIDO [ml/h]")
            with r2:
                render_rate("Carboidrati", carbo_h, "g/h", "CARBO [g/h]")
            with r3:
                render_rate("Sodio", sodio_l, "mg/l", "SODIO [mg/l]")
            with r4:
                render_rate("Calorie", calorie_h, "kcal/h", "CALORIE [kcal/h]")

            if duration_hours <= 0:
                st.info("Durata non impostata: impossibile calcolare i tassi orari.")
            if totals_dict["LIQUIDO [ml]"] <= 0:
                st.info("Inserisci almeno un liquido (ml/unità) per calcolare la concentrazione di sodio (mg/l).")

        def totale_per_prodotto(df: pd.DataFrame) -> pd.DataFrame:
            """Group rows by PRODOTTO, summing quantities — e.g. lo stesso prodotto preso a 0:30
            e di nuovo all'1:00 compare come un'unica riga con quantità 2."""
            if df.empty:
                return pd.DataFrame(
                    columns=["PRODOTTO", "n", "LIQUIDO tot [ml]", "CARBO tot [g]", "SODIO tot [mg]", "CALORIE tot [kcal]"]
                )
            return (
                df.groupby("PRODOTTO", as_index=False)[
                    ["n", "LIQUIDO tot [ml]", "CARBO tot [g]", "SODIO tot [mg]", "CALORIE tot [kcal]"]
                ]
                .sum()
                .sort_values("PRODOTTO")
            )

        def compute_rows_df(items: list) -> pd.DataFrame:
            """Join a list of race_rows dicts with the inventory and compute totals + ORARIO_MIN
            (race-absolute minutes)."""
            df = pd.DataFrame(items)
            if df.empty or "PRODOTTO" not in df.columns:
                return pd.DataFrame(
                    columns=[
                        "PRODOTTO", "SEZIONE", "ORARIO", "ORARIO_MIN", "ORARIO_STR", "n",
                        "LIQUIDO [ml/unita]", "note", "LIQUIDO tot [ml]", "CARBO tot [g]",
                        "SODIO tot [mg]", "CALORIE tot [kcal]",
                    ]
                )
            df = df[df["PRODOTTO"].isin(item_options)].copy()
            if df.empty:
                return df
            if "SEZIONE" not in df.columns:
                df["SEZIONE"] = None
            if "ORARIO" not in df.columns:
                df["ORARIO"] = 0
            df["ORARIO"] = df["ORARIO"].apply(lambda t: int(t) if isinstance(t, (int, float)) else 0)
            if plan_active:
                section_start_by_name = {b["nome"]: b["start"] for b in plan_bounds}
                df["ORARIO_MIN"] = df.apply(
                    lambda r: section_start_by_name.get(r["SEZIONE"], 0) + r["ORARIO"], axis=1
                )
            else:
                df["ORARIO_MIN"] = df["ORARIO"]
            df["ORARIO_STR"] = df["ORARIO_MIN"].apply(minutes_to_hhmm)

            df["n"] = pd.to_numeric(df["n"], errors="coerce").fillna(0.0)
            df["LIQUIDO [ml/unita]"] = pd.to_numeric(df["LIQUIDO [ml/unita]"], errors="coerce").fillna(0.0)

            df = df.join(inv_lookup, on="PRODOTTO")
            df["g CARBO"] = df["g CARBO"].fillna(0.0)
            df["SODIO [mg]"] = df["SODIO [mg]"].fillna(0.0)
            df["CALORIE [kcal]"] = df["CALORIE [kcal]"].fillna(0.0)

            df["LIQUIDO tot [ml]"] = df["LIQUIDO [ml/unita]"] * df["n"]
            df["CARBO tot [g]"] = df["g CARBO"] * df["n"]
            df["SODIO tot [mg]"] = df["SODIO [mg]"] * df["n"]
            df["CALORIE tot [kcal]"] = df["CALORIE [kcal]"] * df["n"]
            return df

        def totals_dict_from(df: pd.DataFrame) -> dict:
            if df.empty:
                return {"LIQUIDO [ml]": 0.0, "g CARBO": 0.0, "SODIO [mg]": 0.0, "CALORIE [kcal]": 0.0}
            return {
                "LIQUIDO [ml]": df["LIQUIDO tot [ml]"].sum(),
                "g CARBO": df["CARBO tot [g]"].sum(),
                "SODIO [mg]": df["SODIO tot [mg]"].sum(),
                "CALORIE [kcal]": df["CALORIE tot [kcal]"].sum(),
            }

        def render_section_totals(df: pd.DataFrame, duration_hours: float):
            render_summary(totals_dict_from(df), duration_hours)
            if not df.empty:
                st.markdown("Totale per prodotto in questa sezione:")
                st.dataframe(
                    totale_per_prodotto(df).style.format(
                        {
                            "n": "{:.2f}",
                            "LIQUIDO tot [ml]": "{:.0f}",
                            "CARBO tot [g]": "{:.1f}",
                            "SODIO tot [mg]": "{:.0f}",
                            "CALORIE tot [kcal]": "{:.0f}",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

        # ---- one flat row of tabs: sections (or "Prodotti"), Totali, Distribuzione oraria ----
        if plan_active:
            tab_labels = list(section_names) + ["📊 Totali", "⏱️ Distribuzione oraria"]
        else:
            tab_labels = ["📦 Prodotti", "📊 Totali", "⏱️ Distribuzione oraria"]
        all_tabs = st.tabs(tab_labels)

        if plan_active:
            n_sections = len(section_names)
            section_tab_objs = all_tabs[:n_sections]
            tab_totals = all_tabs[n_sections]
            tab_hourly = all_tabs[n_sections + 1]
        else:
            tab_prodotti = all_tabs[0]
            tab_totals = all_tabs[1]
            tab_hourly = all_tabs[2]

        # ------------------------------------------------------------ Sezioni / Prodotti
        if plan_active:
            for sec_name, b, sec_tab in zip(section_names, plan_bounds, section_tab_objs):
                with sec_tab:
                    other_sections = [s for s in section_names if s != sec_name]
                    if other_sections:
                        cpy1, cpy2 = st.columns([3, 1])
                        copy_source = cpy1.selectbox(
                            "📋 Copia tutti i prodotti da un'altra sezione",
                            options=["—"] + other_sections,
                            key=f"race_copy_source_{sec_name}",
                        )
                        if cpy2.button("Copia sezione", key=f"race_copy_btn_{sec_name}"):
                            if copy_source != "—":
                                source_items = [
                                    r for r in st.session_state.race_rows if r.get("SEZIONE") == copy_source
                                ]
                                for r in source_items:
                                    rows_to_add.append(
                                        {
                                            "PRODOTTO": r["PRODOTTO"],
                                            "n": r["n"],
                                            "LIQUIDO [ml/unita]": r["LIQUIDO [ml/unita]"],
                                            "note": r["note"],
                                            "SEZIONE": sec_name,
                                            "ORARIO": r.get("ORARIO", 0),
                                        }
                                    )
                            else:
                                st.warning("Scegli prima la sezione sorgente.")

                    sec_items = [r for r in st.session_state.race_rows if r.get("SEZIONE") == sec_name]
                    if not sec_items:
                        st.caption(
                            "Nessun prodotto in questa sezione: aggiungine uno qui sotto, oppure copia "
                            "l'intera lista da un'altra sezione."
                        )
                    for row in sec_items:
                        render_race_row(row, sec_name)

                    if st.button("➕ Aggiungi prodotto", key=f"race_add_{sec_name}"):
                        st.session_state.race_rows.append(
                            {
                                "id": st.session_state.race_next_id,
                                "PRODOTTO": item_options[0] if item_options else None,
                                "n": 1.0,
                                "LIQUIDO [ml/unita]": 0.0,
                                "note": "",
                                "SEZIONE": sec_name,
                                "ORARIO": 0,
                            }
                        )
                        st.session_state.race_next_id += 1
                        st.rerun()

                    sec_df = compute_rows_df(sec_items)
                    st.divider()
                    st.markdown(f"### Totale sezione — {sec_name}")
                    render_section_totals(sec_df, b["durata_min"] / 60.0)
        else:
            with tab_prodotti:
                st.caption(
                    "Per ogni riga: scegli il PRODOTTO dall'inventario, la quantità (n) e, se vuoi calcolare "
                    "anche il liquido, i ml per unità (es. ml d'acqua usati per sciogliere una tavoletta, "
                    "o ml di una borraccia)."
                )
                for row in st.session_state.race_rows:
                    render_race_row(row, None)

                if st.button("➕ Aggiungi prodotto"):
                    st.session_state.race_rows.append(
                        {
                            "id": st.session_state.race_next_id,
                            "PRODOTTO": item_options[0] if item_options else None,
                            "n": 1.0,
                            "LIQUIDO [ml/unita]": 0.0,
                            "note": "",
                            "SEZIONE": None,
                            "ORARIO": 0,
                        }
                    )
                    st.session_state.race_next_id += 1
                    st.rerun()

        if rows_to_add:
            for new_row in rows_to_add:
                new_row["id"] = st.session_state.race_next_id
                st.session_state.race_next_id += 1
                st.session_state.race_rows.append(new_row)
            st.rerun()

        if rows_to_remove:
            st.session_state.race_rows = [
                r for r in st.session_state.race_rows if r["id"] not in rows_to_remove
            ]
            st.rerun()

        # ---- overall totals (used by both the Totali and Distribuzione oraria tabs) ----
        rows = compute_rows_df(st.session_state.race_rows)
        totals = totals_dict_from(rows)

        # ------------------------------------------------------------------ Totali
        with tab_totals:
            with st.expander("🎯 Obiettivi (min / max) — modificabili", expanded=False):
                tcols = st.columns(4)
                for i, key in enumerate(target_labels):
                    with tcols[i]:
                        st.session_state.targets["min"][key] = st.number_input(
                            f"{target_labels[key]} min", value=float(st.session_state.targets["min"][key]), key=f"min_{key}"
                        )
                        st.session_state.targets["max"][key] = st.number_input(
                            f"{target_labels[key]} max", value=float(st.session_state.targets["max"][key]), key=f"max_{key}"
                        )

            if not rows.empty:
                display_cols = ["PRODOTTO"]
                if plan_active:
                    display_cols.append("SEZIONE")
                if time_dist:
                    display_cols.append("ORARIO_STR")
                display_cols += ["n", "LIQUIDO tot [ml]", "CARBO tot [g]", "SODIO tot [mg]", "CALORIE tot [kcal]", "note"]

                st.markdown("**Dettaglio per prodotto**")
                st.dataframe(
                    rows[display_cols].rename(columns={"ORARIO_STR": "ORARIO"}).style.format(
                        {
                            "n": "{:.2f}",
                            "LIQUIDO tot [ml]": "{:.0f}",
                            "CARBO tot [g]": "{:.1f}",
                            "SODIO tot [mg]": "{:.0f}",
                            "CALORIE tot [kcal]": "{:.0f}",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            st.markdown("### Totali generali")
            render_summary(totals, hours)

            if not rows.empty:
                st.markdown("**Totale per prodotto (tutte le sezioni)**")
                st.dataframe(
                    totale_per_prodotto(rows).style.format(
                        {
                            "n": "{:.2f}",
                            "LIQUIDO tot [ml]": "{:.0f}",
                            "CARBO tot [g]": "{:.1f}",
                            "SODIO tot [mg]": "{:.0f}",
                            "CALORIE tot [kcal]": "{:.0f}",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

        # ------------------------------------------------------- Distribuzione oraria
        with tab_hourly:
            if not time_dist:
                st.info(
                    "Attiva \"Vuoi analizzare la distribuzione nel tempo?\" in cima al tab per vedere "
                    "il confronto ora per ora con i tassi orari consigliati."
                )
            else:
                total_minutes = int(round(hours * 60))
                if total_minutes <= 0:
                    st.info("Imposta una durata gara valida (Piano gara o campo Ore corsa) per l'analisi oraria.")
                else:
                    buckets = hourly_buckets(total_minutes)

                    def style_rate_col(col: pd.Series, target_key: str) -> list:
                        tmin = st.session_state.targets["min"][target_key]
                        tmax = st.session_state.targets["max"][target_key]
                        styles = []
                        for v in col:
                            if pd.isna(v):
                                styles.append("")
                            elif v < tmin or v > tmax:
                                styles.append("background-color: #ffd2d2; color: #7a0000;")
                            else:
                                styles.append("background-color: #d7f5d0; color: #175c17;")
                        return styles

                    records = []
                    for i, b in enumerate(buckets):
                        is_first = i == 0
                        if not rows.empty:
                            # ogni fascia è (inizio, fine]: un orario esatto (es. 1:00) appartiene
                            # alla fascia che si conclude in quel momento, non a quella successiva.
                            # La primissima fascia include anche l'istante di partenza (0:00).
                            if is_first:
                                mask = (rows["ORARIO_MIN"] >= b["start"]) & (rows["ORARIO_MIN"] <= b["end"])
                            else:
                                mask = (rows["ORARIO_MIN"] > b["start"]) & (rows["ORARIO_MIN"] <= b["end"])
                            bucket_rows = rows[mask]
                            liquido = bucket_rows["LIQUIDO tot [ml]"].sum()
                            carbo = bucket_rows["CARBO tot [g]"].sum()
                            sodio_tot = bucket_rows["SODIO tot [mg]"].sum()
                            calorie = bucket_rows["CALORIE tot [kcal]"].sum()
                        else:
                            liquido = carbo = sodio_tot = calorie = 0.0
                        bucket_hours = b["durata_min"] / 60.0
                        records.append(
                            {
                                "Fascia": (
                                    f"{minutes_to_hhmm(b['start'])} → {minutes_to_hhmm(b['end'])}"
                                ),
                                "Liquido [ml/h]": liquido / bucket_hours if bucket_hours > 0 else float("nan"),
                                "Carbo [g/h]": carbo / bucket_hours if bucket_hours > 0 else float("nan"),
                                "Sodio [mg/l]": (sodio_tot / liquido * 1000) if liquido > 0 else float("nan"),
                                "Calorie [kcal/h]": calorie / bucket_hours if bucket_hours > 0 else float("nan"),
                            }
                        )
                    hourly_df = pd.DataFrame(records)
                    numeric_cols = ["Liquido [ml/h]", "Carbo [g/h]", "Sodio [mg/l]", "Calorie [kcal/h]"]
                    hourly_df[numeric_cols] = hourly_df[numeric_cols].apply(pd.to_numeric, errors="coerce")

                    st.caption(
                        "🟢 verde = nel range dell'obiettivo · 🔴 rosso = fuori dal range "
                        "(min/max modificabili nel tab Totali)."
                    )

                    # A column that is entirely NaN (e.g. sodium when no liquid was ever taken)
                    # renders as the literal text "None" in Streamlit's dataframe grid instead of
                    # respecting the Styler's format function — so build a text column with the
                    # formatted/placeholder strings up front, and color it using the original
                    # numeric values (captured separately) rather than relying on na_rep/.format().
                    decimals_by_col = {
                        "Liquido [ml/h]": 0,
                        "Carbo [g/h]": 1,
                        "Sodio [mg/l]": 0,
                        "Calorie [kcal/h]": 0,
                    }
                    display_df = hourly_df.copy()
                    for col, decimals in decimals_by_col.items():
                        display_df[col] = hourly_df[col].apply(
                            lambda v, d=decimals: "—" if pd.isna(v) else f"{v:.{d}f}"
                        )

                    styled = display_df.style
                    for col_label, target_key in [
                        ("Liquido [ml/h]", "LIQUIDO [ml/h]"),
                        ("Carbo [g/h]", "CARBO [g/h]"),
                        ("Sodio [mg/l]", "SODIO [mg/l]"),
                        ("Calorie [kcal/h]", "CALORIE [kcal/h]"),
                    ]:
                        numeric_vals = hourly_df[col_label]
                        styled = styled.apply(
                            lambda _col, vals=numeric_vals, k=target_key: style_rate_col(vals, k),
                            subset=[col_label],
                        )
                    st.dataframe(styled, use_container_width=True, hide_index=True)

                    fuori_gara = rows[rows["ORARIO_MIN"] > total_minutes] if not rows.empty else rows
                    if not rows.empty and len(fuori_gara) > 0:
                        nomi = ", ".join(sorted(set(fuori_gara["PRODOTTO"].tolist())))
                        st.warning(
                            f"{len(fuori_gara)} riga/righe hanno un orario oltre la durata totale della gara "
                            f"({minutes_to_hhmm(total_minutes)}) e non compaiono qui sopra: {nomi}."
                        )