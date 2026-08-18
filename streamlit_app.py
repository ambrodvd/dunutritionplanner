"""
Nutri & Drink Calculator
=========================
Streamlit app derived from "NUTRI AND DRINK CALCULATOR v3.0" (Excel).

Two working areas:
- Inventario: list of food/nutrition items (PRODOTTO, MARCA, g CARBO,
  SODIO [mg], CALORIE [kcal] — values are "per unit"), managed with plain
  st.text_input / st.number_input widgets (no editable table/grid).
- Calcolo Corsa: pick items from the inventario, set how many units of each
  you plan to use during the race plus optional liquid (ml) per unit, and
  the app computes total carbs, liquid, sodium and calories, the hourly
  rates, and compares them against configurable min/max targets.
"""

import os

import pandas as pd
import streamlit as st

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
# Session state init
# ----------------------------------------------------------------------------
if "inventario_rows" not in st.session_state:
    st.session_state.inventario_rows = load_inventario_rows()

if "race_rows" not in st.session_state:
    st.session_state.race_rows = [{"id": 0, "PRODOTTO": None, "n": 1.0, "LIQUIDO [ml/unita]": 0.0, "note": ""}]
    st.session_state.race_next_id = 1

if "targets" not in st.session_state:
    st.session_state.targets = {k: dict(v) for k, v in DEFAULT_TARGETS.items()}

if "race_hours" not in st.session_state:
    st.session_state.race_hours = 4.0


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

tab_inv, tab_race = st.tabs(["📦 Inventario", "🏃 Calcoli"])

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
            if c6.button("🗑️", key=f"inv_del_{rid}", help="Rimuovi item"):
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

# ---------------------------------------------------------------- Calcolo Corsa
with tab_race:
    st.subheader("Calcoli")

    inv_df = pd.DataFrame(
        [r for r in st.session_state.inventario_rows if str(r["PRODOTTO"]).strip() != ""]
    )
    if inv_df.empty:
        inv_lookup = pd.DataFrame(columns=["g CARBO", "SODIO [mg]", "CALORIE [kcal]"])
        item_options = []
    else:
        inv_lookup = inv_df.set_index("PRODOTTO")[["g CARBO", "SODIO [mg]", "CALORIE [kcal]"]]
        item_options = sorted(inv_df["PRODOTTO"].unique().tolist())

    if not item_options:
        st.warning("L'inventario è vuoto: aggiungi almeno un item nella tab Inventario.")
    else:
        st.session_state.race_hours = st.number_input(
            "⏱️ Ore corsa (durata gara)",
            min_value=0.0,
            value=float(st.session_state.race_hours),
            step=0.25,
            format="%.2f",
        )

        st.markdown("**Item usati durante la corsa**")
        st.caption(
            "Per ogni riga: scegli il PRODOTTO dall'inventario, la quantità (n) e, se vuoi calcolare "
            "anche il liquido, i ml per unità (es. ml d'acqua usati per sciogliere una tavoletta, "
            "o ml di una borraccia)."
        )

        rows_to_remove = []
        for row in st.session_state.race_rows:
            rid = row["id"]
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([2.2, 1.0, 1.2, 1.8, 0.6])

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
                row["note"] = c4.text_input("note", value=row["note"], key=f"race_note_{rid}")
                c5.write("")
                if c5.button("🗑️", key=f"race_del_{rid}", help="Rimuovi riga"):
                    rows_to_remove.append(rid)

        if rows_to_remove:
            st.session_state.race_rows = [r for r in st.session_state.race_rows if r["id"] not in rows_to_remove]
            st.rerun()

        if st.button("➕ Aggiungi item"):
            st.session_state.race_rows.append(
                {
                    "id": st.session_state.race_next_id,
                    "PRODOTTO": item_options[0] if item_options else None,
                    "n": 1.0,
                    "LIQUIDO [ml/unita]": 0.0,
                    "note": "",
                }
            )
            st.session_state.race_next_id += 1
            st.rerun()

        # ---- compute per-row totals ----
        rows = pd.DataFrame(st.session_state.race_rows)
        rows = rows[rows["PRODOTTO"].isin(item_options)].copy()

        if rows.empty:
            totals = {"LIQUIDO [ml]": 0.0, "g CARBO": 0.0, "SODIO [mg]": 0.0, "CALORIE [kcal]": 0.0}
        else:
            rows["n"] = pd.to_numeric(rows["n"], errors="coerce").fillna(0.0)
            rows["LIQUIDO [ml/unita]"] = pd.to_numeric(rows["LIQUIDO [ml/unita]"], errors="coerce").fillna(0.0)

            rows = rows.join(inv_lookup, on="PRODOTTO")
            rows["g CARBO"] = rows["g CARBO"].fillna(0.0)
            rows["SODIO [mg]"] = rows["SODIO [mg]"].fillna(0.0)
            rows["CALORIE [kcal]"] = rows["CALORIE [kcal]"].fillna(0.0)

            rows["LIQUIDO tot [ml]"] = rows["LIQUIDO [ml/unita]"] * rows["n"]
            rows["CARBO tot [g]"] = rows["g CARBO"] * rows["n"]
            rows["SODIO tot [mg]"] = rows["SODIO [mg]"] * rows["n"]
            rows["CALORIE tot [kcal]"] = rows["CALORIE [kcal]"] * rows["n"]

            display_cols = [
                "PRODOTTO", "n", "LIQUIDO tot [ml]", "CARBO tot [g]", "SODIO tot [mg]", "CALORIE tot [kcal]", "note",
            ]
            st.markdown("**Dettaglio per item**")
            st.dataframe(
                rows[display_cols].style.format(
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

            totals = {
                "LIQUIDO [ml]": rows["LIQUIDO tot [ml]"].sum(),
                "g CARBO": rows["CARBO tot [g]"].sum(),
                "SODIO [mg]": rows["SODIO tot [mg]"].sum(),
                "CALORIE [kcal]": rows["CALORIE tot [kcal]"].sum(),
            }

        st.markdown("### Totali")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Liquido totale", f"{totals['LIQUIDO [ml]']:.0f} ml")
        c2.metric("Carboidrati totali", f"{totals['g CARBO']:.1f} g")
        c3.metric("Sodio totale", f"{totals['SODIO [mg]']:.0f} mg")
        c4.metric("Calorie totali", f"{totals['CALORIE [kcal]']:.0f} kcal")

        hours = st.session_state.race_hours
        liquido_h = totals["LIQUIDO [ml]"] / hours if hours > 0 else None
        carbo_h = totals["g CARBO"] / hours if hours > 0 else None
        calorie_h = totals["CALORIE [kcal]"] / hours if hours > 0 else None
        sodio_l = (totals["SODIO [mg]"] / totals["LIQUIDO [ml]"] * 1000) if totals["LIQUIDO [ml]"] > 0 else None

        st.markdown("### Tassi orari / concentrazione")
        with st.expander("🎯 Obiettivi (min / max) — modificabili", expanded=False):
            tcols = st.columns(4)
            labels = {
                "LIQUIDO [ml/h]": "Liquido [ml/h]",
                "CARBO [g/h]": "Carbo [g/h]",
                "SODIO [mg/l]": "Sodio [mg/l]",
                "CALORIE [kcal/h]": "Calorie [kcal/h]",
            }
            for i, key in enumerate(labels):
                with tcols[i]:
                    st.session_state.targets["min"][key] = st.number_input(
                        f"{labels[key]} min", value=float(st.session_state.targets["min"][key]), key=f"min_{key}"
                    )
                    st.session_state.targets["max"][key] = st.number_input(
                        f"{labels[key]} max", value=float(st.session_state.targets["max"][key]), key=f"max_{key}"
                    )

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

        r1, r2, r3, r4 = st.columns(4)
        with r1:
            render_rate("Liquido", liquido_h, "ml/h", "LIQUIDO [ml/h]")
        with r2:
            render_rate("Carboidrati", carbo_h, "g/h", "CARBO [g/h]")
        with r3:
            render_rate("Sodio", sodio_l, "mg/l", "SODIO [mg/l]")
        with r4:
            render_rate("Calorie", calorie_h, "kcal/h", "CALORIE [kcal/h]")

        if hours <= 0:
            st.info("Inserisci la durata della corsa (ore) per calcolare i tassi orari.")
        if totals["LIQUIDO [ml]"] <= 0:
            st.info("Inserisci almeno un liquido (ml/unità) per calcolare la concentrazione di sodio (mg/l).")