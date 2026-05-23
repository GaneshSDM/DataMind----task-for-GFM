"""
GEMMA 4 (26B) Intent Decomposition & Domain Classifier
Calibration tool — no live data connections.
Agent: ARIA (Analytical Reasoning & Intent Analyst)
"""

import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from config.settings import GEMINI_MODEL
from core.intent_processor import IntentProcessor
from core.report_generator import ReportGenerator
from data.test_scenarios import TEST_SCENARIOS

_CHECKPOINT       = Path(__file__).parent / "batch_checkpoint.json"
_EXCEL_CHECKPOINT = Path(__file__).parent / "excel_batch_checkpoint.json"


def _save_checkpoint(results: list[dict], errors: list[str], path: Path = _CHECKPOINT) -> None:
    path.write_text(
        json.dumps({"results": results, "errors": errors, "saved_at": datetime.now().isoformat()}),
        encoding="utf-8",
    )


def _load_checkpoint(path: Path = _CHECKPOINT) -> tuple[list[dict], list[str], str]:
    if not path.exists():
        return [], [], ""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("results", []), data.get("errors", []), data.get("saved_at", "")


# ── Excel file helpers ────────────────────────────────────────────────────────
_QUERY_KEYWORDS = ["natural language", "query", "input", "question", "nl", "user", "scenario"]
_SR_KEYWORDS    = ["sr", "serial", "no", "num", "id", "row", "s.no"]


def _detect_col(columns: list, keywords: list) -> str | None:
    for col in columns:
        if any(kw in str(col).lower() for kw in keywords):
            return col
    return None


def _load_excel_queries(file_obj) -> tuple[list[dict], str, str | None]:
    """Return (queries, query_col_name, sr_col_name_or_None)."""
    df = pd.read_excel(file_obj, sheet_name=0)
    df.columns = [str(c).strip() for c in df.columns]

    query_col = _detect_col(list(df.columns), _QUERY_KEYWORDS) or df.columns[-1]
    sr_col    = _detect_col(list(df.columns), _SR_KEYWORDS)

    queries = []
    for idx, row in df.iterrows():
        query = str(row[query_col]).strip()
        if not query or query.lower() in ("nan", "none", ""):
            continue
        sr_no = str(row[sr_col]).strip() if sr_col else str(idx + 1)
        # Strip trailing ".0" that pandas adds to integer-read cells
        if sr_no.endswith(".0"):
            sr_no = sr_no[:-2]
        queries.append({"sr_no": sr_no, "query": query})

    return queries, query_col, sr_col

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GEMMA 4 Intent Classifier",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Cached singletons ─────────────────────────────────────────────────────────
@st.cache_resource
def get_processor() -> IntentProcessor:
    return IntentProcessor()


@st.cache_resource
def get_reporter() -> ReportGenerator:
    return ReportGenerator()


# ── Helpers ───────────────────────────────────────────────────────────────────
def result_to_rows(result: dict, scenario_id: str = "", scenario_name: str = "") -> list[dict]:
    rows = []
    for intent in result.get("intents", []):
        rows.append({
            "Scenario": f"[{scenario_id}] {scenario_name}".strip("[] ") if scenario_id else "Custom",
            "Intent #": intent.get("intent_id"),
            "Description": intent.get("description"),
            "Domain": intent.get("domain"),
            "Sub-Domain": intent.get("sub_domain"),
            "Data Source": intent.get("data_source"),
            "Business View": intent.get("structured_view") or "—",
            "Unstructured Source": intent.get("unstructured_source") or "—",
            "Intent Types": ", ".join(intent.get("intent_types", [])),
            "Data Fetch": "Yes" if intent.get("requires_data_fetch") else "No",
            "Reasoning": "Yes" if intent.get("requires_reasoning") else "No",
            "Action": "Yes" if intent.get("requires_action") else "No",
        })
    return rows


def download_button(data: bytes, filename: str) -> None:
    st.download_button(
        label="Download Excel Report",
        data=data,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Configuration")
    st.markdown(f"**Model:** `{GEMINI_MODEL}`")
    st.markdown("**Agent:** ARIA v1.0")
    st.markdown("**Purpose:** Calibration — no live data fetched")
    st.divider()
    mode = st.radio(
        "Analysis Mode",
        ["Single Query", "Batch — All Scenarios", "Excel File Upload"],
        help=(
            "Single: one query at a time. "
            "Batch: run all 20 built-in scenarios. "
            "Excel: upload your own .xlsx file of queries."
        ),
    )
    st.divider()
    st.markdown(
        "**Intent Types**\n"
        "- **Data** — fetch / retrieve\n"
        "- **Reasoning** — analyze / compare\n"
        "- **Action** — create / update / trigger"
    )
    st.markdown(
        "**Data Source**\n"
        "- **Structured** — Business View tables\n"
        "- **Unstructured** — Vector DB / PDFs\n"
        "- **Both** — requires both"
    )

# ── Header ────────────────────────────────────────────────────────────────────
st.title("GEMMA 4 (26B) — Intent Decomposition & Domain Classifier")
st.caption(
    f"Model: {GEMINI_MODEL}  |  Agent: ARIA (Analytical Reasoning & Intent Analyst)  |  "
    f"Calibration mode — classification only, no data retrieval"
)
st.divider()

# ── Single Query Mode ─────────────────────────────────────────────────────────
if mode == "Single Query":
    scenario_options = ["-- Custom input --"] + [
        f"{s['id']} | {s['name']}" for s in TEST_SCENARIOS
    ]
    selected_label = st.selectbox(
        "Select a pre-defined test scenario or choose custom input",
        scenario_options,
    )

    if selected_label != "-- Custom input --":
        idx = scenario_options.index(selected_label) - 1
        prefill = TEST_SCENARIOS[idx]["query"]
        active_scenario = TEST_SCENARIOS[idx]
    else:
        prefill = ""
        active_scenario = None

    query_input = st.text_area(
        "Natural Language Query",
        value=prefill,
        height=110,
        placeholder="Enter your enterprise query here…",
    )

    col_btn, col_info = st.columns([1, 5])
    with col_btn:
        run = st.button("Analyze Intent", type="primary", disabled=not query_input.strip())
    if active_scenario:
        with col_info:
            st.markdown(
                f"Domain: **{active_scenario['domain']}** &nbsp;|&nbsp; "
                f"Complexity: **{active_scenario['complexity']}**"
            )

    if run and query_input.strip():
        with st.spinner("ARIA is analyzing the query…"):
            try:
                processor = get_processor()
                result = processor.process(query_input.strip())
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")
                st.stop()

        s_id = active_scenario["id"] if active_scenario else ""
        s_name = active_scenario["name"] if active_scenario else "Custom Query"

        total = result.get("total_intents", len(result.get("intents", [])))
        st.success(f"Decomposed into **{total} intent(s)**")

        rows = result_to_rows(result, s_id, s_name)
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.warning("Model returned no intents.")

        result["scenario_id"] = s_id
        result["scenario_name"] = s_name
        result["primary_domain"] = active_scenario["domain"] if active_scenario else ""

        excel = get_reporter().generate([result])
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        label = s_id if s_id else "custom"
        download_button(excel, f"intent_report_{label}_{ts}.xlsx")


# ── Batch Mode ────────────────────────────────────────────────────────────────
elif mode == "Batch — All Scenarios":
    st.info(
        f"Batch mode will run all **{len(TEST_SCENARIOS)} scenarios** through GEMMA 4 "
        "sequentially and compile a single Excel report."
    )

    # Auto-reload from disk if session was cleared by a refresh
    if "batch_results" not in st.session_state:
        saved_results, saved_errors, saved_at = _load_checkpoint()
        st.session_state.batch_results = saved_results
        st.session_state.batch_errors = saved_errors
        st.session_state.batch_saved_at = saved_at
    if "batch_errors" not in st.session_state:
        st.session_state.batch_errors = []

    col_run, col_clear = st.columns([2, 1])
    with col_run:
        run_batch = st.button("Run All Scenarios", type="primary")
    with col_clear:
        if st.button("Clear Saved Results", disabled=not _CHECKPOINT.exists()):
            _CHECKPOINT.unlink(missing_ok=True)
            st.session_state.batch_results = []
            st.session_state.batch_errors = []
            st.session_state.batch_saved_at = ""
            st.rerun()

    if run_batch:
        st.session_state.batch_results = []
        st.session_state.batch_errors = []
        st.session_state.batch_saved_at = ""
        _CHECKPOINT.unlink(missing_ok=True)

        progress_bar = st.progress(0, text="Starting batch run…")
        status_placeholder = st.empty()

        processor = get_processor()
        n = len(TEST_SCENARIOS)
        batch_start = time.time()
        log_placeholder = st.empty()
        log_lines: list[str] = []

        for i, scenario in enumerate(TEST_SCENARIOS):
            status_placeholder.markdown(
                f"Running **{scenario['id']}** / {n} — _{scenario['name']}_ &nbsp; "
                f"*(total elapsed: {int(time.time() - batch_start)}s)*"
            )
            t0 = time.time()
            try:
                result = processor.process(scenario["query"])
                result["scenario_id"] = scenario["id"]
                result["scenario_name"] = scenario["name"]
                result["primary_domain"] = scenario.get("domain", "")
                st.session_state.batch_results.append(result)
                elapsed = int(time.time() - t0)
                intents_n = result.get("total_intents", len(result.get("intents", [])))
                log_lines.append(f"[OK] {scenario['id']} — {intents_n} intents — {elapsed}s")
            except Exception as exc:
                elapsed = int(time.time() - t0)
                st.session_state.batch_errors.append(f"{scenario['id']}: {exc}")
                log_lines.append(f"[ERR] {scenario['id']} — ERROR ({elapsed}s): {exc}")

            # Auto-save after every scenario so a refresh never loses progress
            _save_checkpoint(st.session_state.batch_results, st.session_state.batch_errors)
            log_placeholder.code("\n".join(log_lines))
            progress_bar.progress((i + 1) / n, text=f"{i + 1}/{n} done — {int(time.time() - batch_start)}s elapsed")

        status_placeholder.empty()

        if st.session_state.batch_errors:
            st.warning(
                f"{len(st.session_state.batch_errors)} scenario(s) failed:\n\n"
                + "\n".join(st.session_state.batch_errors)
            )

    if st.session_state.batch_results:
        saved_at = st.session_state.get("batch_saved_at", "")
        if saved_at:
            st.info(f"Results restored from last saved session — {saved_at}")

        all_rows: list[dict] = []
        for r in st.session_state.batch_results:
            all_rows.extend(result_to_rows(r, r["scenario_id"], r["scenario_name"]))

        df_all = pd.DataFrame(all_rows)
        total_intents = len(df_all)
        processed = len(st.session_state.batch_results)

        st.success(
            f"Completed **{processed}/{len(TEST_SCENARIOS)}** scenarios — "
            f"**{total_intents}** total intents decomposed"
        )

        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Scenarios Processed", processed)
        with col2:
            st.metric("Total Intents", total_intents)
        with col3:
            st.metric("Avg Intents / Scenario", round(total_intents / processed, 1) if processed else 0)
        with col4:
            structured_pct = (
                round(df_all["Data Source"].eq("Structured").sum() / total_intents * 100, 1)
                if total_intents else 0
            )
            st.metric("Structured Source %", f"{structured_pct}%")

        st.divider()

        # Domain filter
        domain_options = ["All"] + sorted(df_all["Domain"].dropna().unique().tolist())
        selected_domain = st.selectbox("Filter by Domain", domain_options)
        display_df = df_all if selected_domain == "All" else df_all[df_all["Domain"] == selected_domain]

        st.dataframe(display_df, use_container_width=True, hide_index=True, height=500)

        excel = get_reporter().generate(st.session_state.batch_results)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        download_button(excel, f"intent_report_batch_{ts}.xlsx")


# ── Excel File Upload Mode ────────────────────────────────────────────────────
else:
    st.markdown("### Upload your Excel file of queries")
    st.caption(
        "File must contain a column with natural language queries. "
        "A SR.No / ID column is optional — if present it will be used as the Scenario ID in the output."
    )

    uploaded_file = st.file_uploader(
        "Drop your .xlsx file here",
        type=["xlsx", "xls"],
        help="One query per row. The app auto-detects the query column by its header name.",
    )

    if uploaded_file:
        try:
            queries, q_col, sr_col = _load_excel_queries(uploaded_file)
        except Exception as exc:
            st.error(f"Could not read file: {exc}")
            st.stop()

        st.success(
            f"Loaded **{len(queries)} queries** — "
            f"query column: `{q_col}` | "
            f"SR.No column: `{sr_col if sr_col else 'not found — using row number'}`"
        )

        # Preview table
        with st.expander("Preview loaded queries", expanded=True):
            preview_df = pd.DataFrame(queries).rename(columns={"sr_no": "SR.No", "query": "Query"})
            st.dataframe(preview_df, use_container_width=True, hide_index=True, height=220)

        # Auto-reload checkpoint if session refreshed
        if "excel_results" not in st.session_state:
            saved_r, saved_e, saved_at = _load_checkpoint(_EXCEL_CHECKPOINT)
            st.session_state.excel_results  = saved_r
            st.session_state.excel_errors   = saved_e
            st.session_state.excel_saved_at = saved_at
        if "excel_errors" not in st.session_state:
            st.session_state.excel_errors = []

        col_run, col_clear = st.columns([2, 1])
        with col_run:
            run_excel = st.button(
                f"Run Analysis on {len(queries)} queries", type="primary"
            )
        with col_clear:
            if st.button("Clear Saved Results ", disabled=not _EXCEL_CHECKPOINT.exists()):
                _EXCEL_CHECKPOINT.unlink(missing_ok=True)
                st.session_state.excel_results  = []
                st.session_state.excel_errors   = []
                st.session_state.excel_saved_at = ""
                st.rerun()

        if run_excel:
            st.session_state.excel_results  = []
            st.session_state.excel_errors   = []
            st.session_state.excel_saved_at = ""
            _EXCEL_CHECKPOINT.unlink(missing_ok=True)

            progress_bar     = st.progress(0, text="Starting…")
            status_ph        = st.empty()
            log_ph           = st.empty()
            log_lines: list[str] = []
            batch_start      = time.time()
            processor        = get_processor()
            n                = len(queries)

            for i, item in enumerate(queries):
                sr_no = item["sr_no"]
                query = item["query"]
                status_ph.markdown(
                    f"Running **SR.No {sr_no}** / {n} &nbsp; "
                    f"*(elapsed: {int(time.time() - batch_start)}s)*"
                )
                t0 = time.time()
                try:
                    result = processor.process(query)
                    # Use SR.No as scenario_id; truncated query as scenario_name
                    result["scenario_id"]   = sr_no
                    result["scenario_name"] = query[:55] + ("…" if len(query) > 55 else "")
                    result["primary_domain"] = (
                        result["intents"][0]["domain"] if result.get("intents") else ""
                    )
                    st.session_state.excel_results.append(result)
                    elapsed  = int(time.time() - t0)
                    intents_n = result.get("total_intents", len(result.get("intents", [])))
                    log_lines.append(f"[OK]  SR {sr_no:>3} — {intents_n} intents — {elapsed}s")
                except Exception as exc:
                    elapsed = int(time.time() - t0)
                    st.session_state.excel_errors.append(f"SR {sr_no}: {exc}")
                    log_lines.append(f"[ERR] SR {sr_no:>3} — ERROR ({elapsed}s): {exc}")

                _save_checkpoint(
                    st.session_state.excel_results,
                    st.session_state.excel_errors,
                    _EXCEL_CHECKPOINT,
                )
                log_ph.code("\n".join(log_lines))
                progress_bar.progress(
                    (i + 1) / n,
                    text=f"{i + 1}/{n} done — {int(time.time() - batch_start)}s elapsed",
                )

            status_ph.empty()
            if st.session_state.excel_errors:
                st.warning(
                    f"{len(st.session_state.excel_errors)} query(ies) failed:\n\n"
                    + "\n".join(st.session_state.excel_errors)
                )

        if st.session_state.get("excel_results"):
            saved_at = st.session_state.get("excel_saved_at", "")
            if saved_at:
                st.info(f"Results restored from last saved session — {saved_at}")

            all_rows: list[dict] = []
            for r in st.session_state.excel_results:
                all_rows.extend(result_to_rows(r, r["scenario_id"], r["scenario_name"]))

            df_all        = pd.DataFrame(all_rows)
            total_intents = len(df_all)
            processed     = len(st.session_state.excel_results)

            st.success(
                f"Completed **{processed}/{len(queries)}** queries — "
                f"**{total_intents}** total intents decomposed"
            )

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Queries Processed", processed)
            with col2:
                st.metric("Total Intents", total_intents)
            with col3:
                st.metric("Avg Intents / Query", round(total_intents / processed, 1) if processed else 0)
            with col4:
                structured_pct = (
                    round(df_all["Data Source"].eq("Structured").sum() / total_intents * 100, 1)
                    if total_intents else 0
                )
                st.metric("Structured Source %", f"{structured_pct}%")

            st.divider()

            domain_options = ["All"] + sorted(df_all["Domain"].dropna().unique().tolist())
            selected_domain = st.selectbox("Filter by Domain", domain_options, key="excel_domain_filter")
            display_df = df_all if selected_domain == "All" else df_all[df_all["Domain"] == selected_domain]

            st.dataframe(display_df, use_container_width=True, hide_index=True, height=500)

            excel_bytes = get_reporter().generate(st.session_state.excel_results)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            download_button(excel_bytes, f"intent_report_excel_{ts}.xlsx")
