"""
SQL Generator Agent — Test Harness
Streamlit UI: two tabs
  Generate : pick example → configure RLS/CLS → generate SQL → compare → score
  Correct  : pick validation error example → apply LLM correction → show fixed SQL
"""

import os
import re
import json
import random
import difflib

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sql_agent import (
    load_schema_reference, resolve_tables,
    generate_sql, get_provider, run_correction,
)

load_dotenv()

# ── Data loaders ──────────────────────────────────────────────────────────────
@st.cache_data
def get_examples():
    with open("examples.json", "r", encoding="utf-8") as f:
        return json.load(f)["examples"]

@st.cache_data
def get_correction_examples():
    with open("correction_examples.json", "r", encoding="utf-8") as f:
        return json.load(f)["examples"]

@st.cache_data
def get_schema():
    return load_schema_reference()


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_all_columns(schema_ref, table_names):
    cols   = []
    target = {t.split(".")[-1].lower() for t in table_names}
    for catalog in schema_ref["catalog"]:
        for sub in catalog["sub_domains"]:
            for tbl in sub["tables"]:
                if tbl["table_name"].lower() in target:
                    cols.extend(c["name"] for c in tbl["columns"])
    return sorted(set(cols))


def build_input(ex, rls_enabled, rls_filters, cls_enabled, cls_columns):
    table_names = [t.split(".")[-1] for t in ex["tables_used"]]
    rls = {"enabled": False, "filters": [], "policy_name": None}
    if rls_enabled and rls_filters:
        rls = {"enabled": True, "policy_name": "ui_rls_policy", "filters": rls_filters}
    cls = {"enabled": False, "restricted_columns": [], "policy_name": None}
    if cls_enabled and cls_columns:
        cls = {"enabled": True, "policy_name": "ui_cls_policy", "restricted_columns": cls_columns}
    return {
        "request_id": f"example-{ex['id']}",
        "prompt":     ex["prompt"],
        "domain":     "Sales",
        "sub_domain": "Sales Analytics",
        "tables":     table_names,
        "row_level_security":    rls,
        "column_level_security": cls,
    }


def extract_select_columns(sql):
    sql_clean = re.sub(r"--[^\n]*", " ", sql)
    sql_clean = re.sub(r"\s+", " ", sql_clean).strip()
    match = re.search(r"(?:^|\)\s*)select\s+(.*?)\s+from\s", sql_clean, re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    select_clause = match.group(1).strip()
    cols, depth, buf = [], 0, ""
    for ch in select_clause:
        if ch == "(":   depth += 1
        elif ch == ")": depth -= 1
        if ch == "," and depth == 0:
            cols.append(buf.strip()); buf = ""
        else:
            buf += ch
    if buf.strip():
        cols.append(buf.strip())
    names = []
    for col in cols:
        col   = col.strip()
        alias = re.search(r"\bas\s+([`\"\w]+)$", col, re.IGNORECASE)
        if alias:
            names.append(alias.group(1).strip('`"'))
        else:
            tokens = re.findall(r"[\w]+", col)
            if tokens:
                names.append(tokens[-1].lower())
    return names


def score_output_match(generated_sql, expected_sample):
    expected_cols  = [c.lower() for c in expected_sample["columns"]]
    generated_cols = [c.lower() for c in extract_select_columns(generated_sql)]
    if not expected_cols:
        return {"col_match_pct": 100.0, "matched": [], "missing": [], "extra": [],
                "expected_cols": [], "generated_cols": []}
    matched = [c for c in expected_cols if c in generated_cols]
    missing = [c for c in expected_cols if c not in generated_cols]
    extra   = [c for c in generated_cols if c not in expected_cols]
    return {
        "col_match_pct":  round(100.0 * len(matched) / len(expected_cols), 1),
        "expected_cols":  expected_cols,
        "generated_cols": generated_cols,
        "matched": matched, "missing": missing, "extra": extra,
    }


def normalize_sql(sql):
    sql = sql.lower().strip()
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"\s+", " ", sql)
    sql = re.sub(r"[;\s]+$", "", sql)
    return sql


def score_accuracy(generated, expected):
    gen = normalize_sql(generated)
    exp = normalize_sql(expected)
    str_score   = difflib.SequenceMatcher(None, gen, exp).ratio()
    gen_tokens  = set(re.findall(r"\b\w+\b", gen))
    exp_tokens  = set(re.findall(r"\b\w+\b", exp))
    token_score = len(gen_tokens & exp_tokens) / len(exp_tokens) if exp_tokens else 0
    clauses     = ["select", "from", "where", "group by", "order by", "having",
                   "join", "left join", "inner join", "with", "over", "partition by",
                   "limit", "distinct", "case when"]
    exp_clauses   = [c for c in clauses if c in exp]
    gen_clauses   = [c for c in clauses if c in gen]
    clause_score  = (len(set(exp_clauses) & set(gen_clauses)) / len(exp_clauses)
                     if exp_clauses else 1.0)
    return {
        "overall":           round((str_score * 0.5 + token_score * 0.3 + clause_score * 0.2) * 100, 1),
        "string_similarity": round(str_score   * 100, 1),
        "token_overlap":     round(token_score * 100, 1),
        "clause_match":      round(clause_score * 100, 1),
    }


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="SQL Generator — Test Harness", page_icon="🧪", layout="wide")
st.title("🧪 SQL Generator Agent — Test Harness")
st.caption("Generate: pick example → configure security → generate SQL | Correct: pick validation error → apply LLM fix")

examples            = get_examples()
correction_examples = get_correction_examples()
schema_ref          = get_schema()

tab_gen, tab_corr = st.tabs(["▶ Generate", "🔧 Correct"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — GENERATE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_gen:

    st.subheader("1. Select Example")
    gen_options  = {f"#{ex['id']:02d} — {ex['prompt']}": ex for ex in examples}
    gen_key      = st.selectbox("Example", list(gen_options.keys()), label_visibility="collapsed", key="gen_select")
    selected_ex  = gen_options[gen_key]

    with st.expander("Example details", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Prompt**");           st.info(selected_ex["prompt"])
            st.markdown("**Tables in scope**");  st.code(", ".join(selected_ex["tables_used"]))
        with c2:
            st.markdown("**Expected SQL**");     st.code(selected_ex["expected_sql"], language="sql")

    st.subheader("2. Configure Security Context")
    all_columns = get_all_columns(schema_ref, selected_ex["tables_used"])
    default_rls = selected_ex.get("rls_filters", [])
    default_cls = selected_ex.get("excluded_columns", [])

    rls_col, cls_col = st.columns(2)

    with rls_col:
        st.markdown("#### Row Level Security (RLS)")
        rls_enabled = st.toggle("Enable RLS", value=bool(default_rls), key="rls_toggle")
        rls_filters = []
        if rls_enabled:
            if "rls_rows" not in st.session_state or st.session_state.get("last_example") != selected_ex["id"]:
                st.session_state["rls_rows"]    = default_rls or [{"column": "", "operator": "IN", "values": [], "value": ""}]
                st.session_state["last_example"] = selected_ex["id"]
            col_add, col_clear = st.columns(2)
            if col_add.button("+ Add Filter",  key="add_rls"):
                st.session_state["rls_rows"].append({"column": "", "operator": "IN", "values": [], "value": ""})
            if col_clear.button("Clear All",   key="clear_rls"):
                st.session_state["rls_rows"] = []
            rows_to_remove = []
            for i, row in enumerate(st.session_state["rls_rows"]):
                fc, oc, vc, dc = st.columns([3, 2, 4, 1])
                col_val = fc.text_input("Column", value=row.get("column", ""), key=f"rls_col_{i}", placeholder="e.g. country")
                op_val  = oc.selectbox("Op", ["IN", "=", "!=", ">", ">=", "<", "<="], key=f"rls_op_{i}",
                                       index=["IN","=","!=",">",">=","<","<="].index(row.get("operator","IN")))
                if op_val == "IN":
                    raw = vc.text_input("Values (comma-sep)", value=", ".join(row.get("values", [])), key=f"rls_val_{i}", placeholder="USA, Canada")
                    rls_filters.append({"column": col_val, "operator": "IN", "values": [v.strip() for v in raw.split(",") if v.strip()]})
                else:
                    single = vc.text_input("Value", value=row.get("value", ""), key=f"rls_val_{i}")
                    rls_filters.append({"column": col_val, "operator": op_val, "value": single})
                if dc.button("X", key=f"rls_del_{i}"):
                    rows_to_remove.append(i)
            for i in sorted(rows_to_remove, reverse=True):
                st.session_state["rls_rows"].pop(i)
            if rls_filters:
                st.caption(f"Active filters: {len(rls_filters)}")

    with cls_col:
        st.markdown("#### Column Level Security (CLS)")
        cls_enabled = st.toggle("Enable CLS", value=bool(default_cls), key="cls_toggle")
        cls_columns = []
        if cls_enabled:
            cls_columns = st.multiselect(
                "Restrict / exclude columns", options=all_columns,
                default=[c for c in default_cls if c in all_columns], key="cls_multiselect",
            )
            if cls_columns:
                st.caption(f"{len(cls_columns)} column(s) will be excluded from schema and SELECT.")

    st.subheader("3. Generate SQL")
    if st.button("Generate SQL", type="primary", key="gen_btn"):
        try:
            provider, model, client = get_provider()
        except EnvironmentError as e:
            st.error(str(e)); st.stop()

        input_data = build_input(selected_ex, rls_enabled, rls_filters, cls_enabled, cls_columns)
        resolved   = resolve_tables(schema_ref, "Sales", input_data["tables"])
        if not resolved:
            st.error(f"Tables not found in schema_reference: {input_data['tables']}"); st.stop()

        shots = random.sample([e for e in examples if e["id"] != selected_ex["id"]], min(6, len(examples) - 1))
        with st.spinner(f"Calling {provider.upper()} API ({model})..."):
            sql, excluded_cols, rls_where, rls_cfg, cls_cfg = generate_sql(
                provider, client, model, input_data, resolved, shots
            )

        scores     = score_accuracy(sql, selected_ex["expected_sql"])
        out_scores = score_output_match(sql, selected_ex["sample_output"])
        combined   = round(
            scores["string_similarity"] * 0.40 + scores["token_overlap"] * 0.20 +
            scores["clause_match"]      * 0.15 + out_scores["col_match_pct"] * 0.25, 1
        )

        st.divider(); st.subheader("4. Accuracy Score")
        badge = "🟢" if combined >= 75 else "🟡" if combined >= 50 else "🔴"
        st.markdown(f"## {badge} Combined Score: **{combined}%**")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Combined",       f"{combined}%")
        m2.metric("SQL Similarity", f"{scores['string_similarity']}%")
        m3.metric("Token Overlap",  f"{scores['token_overlap']}%")
        m4.metric("Clause Match",   f"{scores['clause_match']}%")
        m5.metric("Column Match",   f"{out_scores['col_match_pct']}%")

        st.divider(); st.subheader("5. SQL Comparison")
        col_gen, col_exp = st.columns(2)
        with col_gen:
            st.markdown("**Generated SQL**"); st.code(sql, language="sql")
        with col_exp:
            st.markdown("**Expected SQL**");  st.code(selected_ex["expected_sql"], language="sql")
        with st.expander("Unified Diff (expected → generated)"):
            diff_lines = list(difflib.unified_diff(
                normalize_sql(selected_ex["expected_sql"]).split(),
                normalize_sql(sql).split(), fromfile="expected", tofile="generated", lineterm="",
            ))
            st.code("\n".join(diff_lines) if diff_lines else "No diff — identical after normalization", language="diff")

        st.divider(); st.subheader("6. Output Comparison")
        oc1, oc2 = st.columns(2)
        with oc1:
            st.markdown("**Expected Sample Output**")
            sample = selected_ex["sample_output"]
            st.dataframe(pd.DataFrame(sample["rows"], columns=sample["columns"]), use_container_width=True)
        with oc2:
            st.markdown("**Generated SQL — Output Schema**")
            gen_cols, exp_cols = out_scores["generated_cols"], out_scores["expected_cols"]
            col_status = ([{"column": c, "status": "matched"} for c in gen_cols if c in exp_cols] +
                          [{"column": c, "status": "extra"}   for c in gen_cols if c not in exp_cols] +
                          [{"column": c, "status": "missing"} for c in out_scores["missing"]])
            st.dataframe(pd.DataFrame(col_status), use_container_width=True)
            if out_scores["missing"]: st.warning(f"Missing: {', '.join(out_scores['missing'])}")
            if out_scores["extra"]:   st.info(f"Extra: {', '.join(out_scores['extra'])}")

        st.divider(); st.subheader("7. Security Context Applied")
        s1, s2 = st.columns(2)
        with s1:
            st.markdown("**RLS**")
            st.json({"enabled": rls_cfg.get("enabled"), "policy": rls_cfg.get("policy_name"),
                     "where_injected": rls_where, "filters": rls_cfg.get("filters", [])})
        with s2:
            st.markdown("**CLS**")
            st.json({"enabled": cls_cfg.get("enabled"), "policy": cls_cfg.get("policy_name"),
                     "columns_excluded": excluded_cols})


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CORRECT
# ═══════════════════════════════════════════════════════════════════════════════
with tab_corr:

    st.subheader("1. Select Validation Error Example")

    ERROR_BADGE = {"SCHEMA": "🟠 SCHEMA", "SYNTAX": "🔴 SYNTAX",
                   "RLS": "🔒 RLS", "CLS": "🔑 CLS", "FILTER": "🟡 FILTER"}

    corr_options = {
        f"#{ex['id']:02d} [{ERROR_BADGE.get(ex['error_type'], ex['error_type'])}] — {ex['validation_hints']['original_prompt']}": ex
        for ex in correction_examples
    }
    corr_key    = st.selectbox("Correction example", list(corr_options.keys()),
                               label_visibility="collapsed", key="corr_select")
    selected_ce = corr_options[corr_key]

    st.subheader("2. Validation Errors Found")
    err_col, sug_col = st.columns(2)
    with err_col:
        st.markdown("**Validation Errors**")
        for err in selected_ce["validation_errors"]:
            badge = ERROR_BADGE.get(err["type"], err["type"])
            st.error(f"**{badge}**  {err['detail']}")
    with sug_col:
        st.markdown("**Suggested Corrections**")
        for s in selected_ce["suggested_corrections"]:
            st.info(s)

    st.subheader("3. Faulty SQL")
    st.code(selected_ce["generated_sql"], language="sql")

    with st.expander("Security context (from validator)", expanded=False):
        sc1, sc2 = st.columns(2)
        with sc1:
            st.markdown("**RLS applied**")
            st.json(selected_ce["rls_applied"])
        with sc2:
            st.markdown("**CLS applied**")
            st.json(selected_ce["cls_applied"])

    st.subheader("4. Apply Correction")
    if st.button("Apply Correction", type="primary", key="corr_btn"):
        try:
            get_provider()  # verify key exists before spinner
        except EnvironmentError as e:
            st.error(str(e)); st.stop()

        with st.spinner("Re-generating corrected SQL via LLM..."):
            try:
                result = run_correction(selected_ce, schema_ref=schema_ref)
                corrected_sql = result["corrected_sql"]
                st.success("Correction applied.")
            except Exception as e:
                st.error(f"Correction failed: {e}"); st.stop()

        st.divider(); st.subheader("5. Corrected SQL")
        fix_col, orig_col = st.columns(2)
        with fix_col:
            st.markdown("**Corrected SQL**")
            st.code(corrected_sql, language="sql")
        with orig_col:
            st.markdown("**Original Faulty SQL**")
            st.code(selected_ce["generated_sql"], language="sql")

        with st.expander("Diff (faulty → corrected)"):
            diff_lines = list(difflib.unified_diff(
                normalize_sql(selected_ce["generated_sql"]).split(),
                normalize_sql(corrected_sql).split(),
                fromfile="faulty", tofile="corrected", lineterm="",
            ))
            st.code("\n".join(diff_lines) if diff_lines else "No diff", language="diff")

        st.divider(); st.subheader("6. Errors Addressed")
        for err in result["errors_addressed"]:
            badge = ERROR_BADGE.get(err["type"], err["type"])
            st.success(f"**{badge}** resolved — {err['detail']}")
