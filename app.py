from __future__ import annotations

from datetime import datetime, timezone
import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from fund_analyzer.ai.client import AIClient
from fund_analyzer.cash_flow_input import parse_cash_flow_rows
from fund_analyzer.config import AppConfig
from fund_analyzer.identity import rank_matches
from fund_analyzer.models import AnalysisStatus, CashFlowKind, EvidenceKind, ProductIdentity, ProductType
from fund_analyzer.orchestration import AnalysisRequest, FundAnalyzer, Services
from fund_analyzer.reporting import build_report_view
from fund_analyzer.sources.amfi import AmfiCollector
from fund_analyzer.sources.apmi import ApmiCollector
from fund_analyzer.sources.nifty import NiftyCollector
from fund_analyzer.sources.public_page import PublicPageCollector


TYPE_LABELS = {"Mutual Fund": ProductType.MUTUAL_FUND, "PMS": ProductType.PMS, "AIF": ProductType.AIF}


@st.cache_resource(show_spinner=False)
def load_ai():
    try:
        config = AppConfig.load(st.secrets)
        if config.api_key == "replace-locally":
            return None
        return AIClient(config)
    except Exception:
        return None


@st.cache_data(ttl=21600, show_spinner=False)
def cached_amfi_directory():
    return AmfiCollector().directory().products


@st.cache_data(ttl=21600, show_spinner=False)
def cached_apmi_rows():
    return ApmiCollector().performance()


def services() -> Services:
    return Services(amfi=AmfiCollector(), apmi=ApmiCollector(), public_page=PublicPageCollector(), nifty=NiftyCollector(), ai=load_ai())


def find_candidates(product_type: ProductType, query: str, provider: str) -> tuple[list[ProductIdentity], str | None]:
    try:
        if product_type is ProductType.MUTUAL_FUND:
            products = cached_amfi_directory()
            return [match.identity for match in rank_matches(query, products)[:12] if match.score >= 55], None
        if product_type is ProductType.PMS:
            rows = cached_apmi_rows()
            products = [ProductIdentity(product_type=ProductType.PMS, name=row["approach"], provider=row["provider"]) for row in rows if row["approach"]]
            return [match.identity for match in rank_matches(query, products)[:12] if match.score >= 55], None
        if not provider.strip():
            return [], "Enter the AIF manager name so the uploaded factsheet can be identity-checked."
        return [ProductIdentity(product_type=ProductType.AIF, name=query.strip(), provider=provider.strip())], "SEBI registration should be verified from the factsheet or public URL."
    except Exception as exc:
        return [], f"Product directory unavailable: {type(exc).__name__}. Check your connection and try again."


def _on_product_type_change():
    st.session_state.candidates = []
    st.session_state.report = None
    st.session_state.pop("confirmed_product", None)
    st.session_state.search_warning = None


def suggested_benchmark(identity: ProductIdentity) -> str:
    text = f"{identity.category or ''} {identity.name}".lower()
    if any(word in text for word in ("small cap", "smallcap")):
        return "Nifty Smallcap 250 TRI"
    if any(word in text for word in ("mid cap", "midcap")):
        return "Nifty Midcap 150 TRI"
    if any(word in text for word in ("debt", "bond", "gilt", "liquid")):
        return "Product-disclosed debt TRI"
    if "hybrid" in text or "balanced" in text:
        return "Product-disclosed hybrid benchmark"
    return identity.benchmark or "Nifty 500 TRI"


def badge(label: str, tone: str = "blue") -> str:
    return f'<span class="badge {tone}">{html.escape(label)}</span>'


def render_report(report):
    status_tone = {AnalysisStatus.COMPLETE: "success", AnalysisStatus.PARTIAL: "warning", AnalysisStatus.INSUFFICIENT: "error", AnalysisStatus.SOURCE_UNAVAILABLE: "error"}[report.status]
    getattr(st, status_tone)(report.status.value)
    st.markdown(f"## {html.escape(report.identity.name)}")
    st.caption(f"{report.identity.provider} · {report.identity.product_type.value.replace('_', ' ').title()} · Session-only report")

    identity_cols = st.columns(4)
    identity_cols[0].metric("Category", report.identity.category or "Not verified")
    identity_cols[1].metric("Plan", report.identity.plan or "Not applicable")
    identity_cols[2].metric("Option", report.identity.option or "Not applicable")
    identity_cols[3].metric("Registration / code", report.identity.registration_id or report.identity.scheme_code or "Not verified")

    if report.chart:
        figure = go.Figure()
        if report.chart.kind == "cash_flow_timeline":
            points = report.chart.product
            figure.add_trace(go.Bar(
                x=[point.date for point in points],
                y=[point.value for point in points],
                name="Dated cash flow / residual value",
                marker_color=["#EF4444" if point.value < 0 else "#10B981" for point in points],
            ))
            figure.update_layout(yaxis_title="Amount (INR)", barmode="relative")
        else:
            range_key = st.segmented_control("History", ["1Y", "3Y", "5Y", "Max"], default="Max", key="range")
            view = build_report_view(report, range_key or "Max")
            figure.add_trace(go.Scatter(x=[point.date for point in view.chart.product], y=[point.value for point in view.chart.product], name="Product", line={"color": "#5B5CF6", "width": 2.5}))
            if view.chart.benchmark:
                figure.add_trace(go.Scatter(x=[point.date for point in view.chart.benchmark], y=[point.value for point in view.chart.benchmark], name="Benchmark", line={"color": "#94A3B8", "width": 2}))
            figure.update_layout(yaxis_title="Growth of ₹1 lakh", legend_orientation="h", hovermode="x unified")
        figure.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(figure, width="stretch")
    else:
        st.info("A NAV-style chart is not shown because the available evidence does not contain a defensible continuous performance series.")

    valid_metrics = [metric for metric in report.metrics if metric.value is not None]
    if valid_metrics:
        cols = st.columns(min(4, len(valid_metrics)))
        for index, metric in enumerate(valid_metrics):
            value = metric.value
            if metric.unit == "%":
                display = f"{value * 100:.2f}%"
            elif metric.unit == "x":
                display = f"{value:.2f}x"
            else:
                display = f"{value:.2f}"
            cols[index % len(cols)].metric(metric.label, display, help=f"As of {metric.as_of}" if metric.as_of else None)

    st.markdown("### Investment case")
    pros_col, cons_col = st.columns(2)
    with pros_col:
        st.markdown('<div class="case-card pros"><h4>PROS</h4>', unsafe_allow_html=True)
        if report.ai and report.ai.available:
            for item in report.ai.pros:
                st.markdown(f"- {badge('AI Assessment')} {html.escape(item.text)}", unsafe_allow_html=True)
        elif report.ai and not report.ai.available and report.ai.limitations:
            st.caption("AI assessment failed — " + " ".join(report.ai.limitations))
        else:
            st.caption("Configure the AI endpoint to generate an independent assessment.")
        st.markdown("</div>", unsafe_allow_html=True)
    with cons_col:
        st.markdown('<div class="case-card cons"><h4>CONS</h4>', unsafe_allow_html=True)
        if report.ai and report.ai.available:
            for item in report.ai.cons:
                st.markdown(f"- {badge('AI Assessment', 'amber')} {html.escape(item.text)}", unsafe_allow_html=True)
        elif report.ai and not report.ai.available and report.ai.limitations:
            st.caption("AI assessment failed — verified evidence below remains usable.")
        else:
            st.caption("No AI assessment is available; verified evidence remains below.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### 3–5 Year View")
    if report.ai and report.ai.available and report.ai.outlook:
        st.markdown(f"{badge('AI Assessment')} {html.escape(report.ai.outlook.text)}", unsafe_allow_html=True)
        with st.expander("Risks and conditions to monitor"):
            for item in [*report.ai.risks, *report.ai.monitoring]:
                st.markdown(f"- {html.escape(item.text)}")
    elif report.ai and not report.ai.available and report.ai.limitations:
        st.info("AI view unavailable (" + " ".join(report.ai.limitations) + ") The report does not replace it with an invented conclusion.")
    else:
        st.info("AI view unavailable. The report does not replace it with an invented conclusion.")

    if report.warnings:
        with st.expander("Data gaps and warnings", expanded=True):
            for warning in report.warnings:
                st.markdown(f"- {html.escape(warning)}")

    with st.expander(f"Evidence and sources ({len(report.evidence)})"):
        for item in report.evidence:
            label = {
                EvidenceKind.VERIFIED_FACT: "Verified fact",
                EvidenceKind.CALCULATED_METRIC: "Calculated metric",
                EvidenceKind.USER_INPUT: "User input",
                EvidenceKind.DOCUMENT_EXTRACT: "OCR extract - verify",
                EvidenceKind.AI_ASSESSMENT: "AI assessment",
            }[item.kind]
            link = f"[source]({item.source.url})" if item.source.url else item.source.title
            page = f", page {item.source.page}" if item.source.page else ""
            confidence = f" · extraction confidence {item.confidence:.0%}" if item.confidence < 1 else ""
            st.markdown(f"{badge(label)} **{html.escape(item.label)}:** {html.escape(str(item.value))} {html.escape(item.unit or '')}  \n{link} · observed {item.source.observed_at}{page} · retrieved {item.source.retrieved_at.date()}{confidence}", unsafe_allow_html=True)

    st.caption("Research tool only. Past performance may not be sustained. AI assessments may be wrong and are not investment advice.")


st.set_page_config(page_title="Indian Fund Analyzer", page_icon="📊", layout="wide")
st.markdown("""
<style>
.block-container {max-width: 1280px; padding-top: 2rem; padding-bottom: 4rem}
.hero {padding: 1.5rem 1.75rem; border-radius: 18px; background: linear-gradient(135deg,#111827,#312E81); color:white; margin-bottom:1.25rem}
.hero h1 {margin:0; font-size:2rem}.hero p {opacity:.82; margin:.4rem 0 0}
.case-card {padding:1rem 1.2rem; border:1px solid; border-radius:14px; min-height:170px; background:white}.pros{border-color:#34D399}.cons{border-color:#F87171}
.badge{display:inline-block;padding:.12rem .45rem;border-radius:999px;background:#EEF2FF;color:#4338CA;font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em}.badge.amber{background:#FFF7ED;color:#C2410C}
</style>
<div class="hero"><h1>Indian Fund Analyzer</h1><p>Evidence-first research for one mutual fund, PMS strategy, or AIF. Nothing is saved.</p></div>
""", unsafe_allow_html=True)

if "candidates" not in st.session_state:
    st.session_state.candidates = []
if "report" not in st.session_state:
    st.session_state.report = None

input_card = st.container(border=True)
with input_card:
    left, right = st.columns([1, 2])
    product_label = left.selectbox("Product type", list(TYPE_LABELS), key="product_type", on_change=_on_product_type_change)
    query = right.text_input("Product or strategy name", placeholder="e.g. Parag Parikh Flexi Cap Fund")
    provider = st.text_input("Manager / AMC (required for manual AIF lookup)", placeholder="e.g. Example Capital")
    public_url = st.text_input("Official website or factsheet URL (optional)", placeholder="https://...")
    pdf = st.file_uploader("Factsheet PDF (optional, text or scanned, max 15 MB)", type=["pdf"])
    st.caption("Scanned pages are OCR-processed on this computer only. OCR fields are flagged for manual verification.")
    cash_flow_rows = None
    if TYPE_LABELS[product_label] is ProductType.AIF:
        st.markdown("#### Dated AIF cash flows")
        st.info("Enter positive amounts. Contribution rows are treated as investor outflows; distributions and the single terminal residual value are inflows.")
        cash_flow_rows = st.data_editor(
            pd.DataFrame({
                "date": pd.Series(dtype="datetime64[ns]"),
                "kind": pd.Series(dtype="string"),
                "amount": pd.Series(dtype="float64"),
                "note": pd.Series(dtype="string"),
            }),
            key="aif_cash_flow_editor",
            num_rows="dynamic",
            hide_index=True,
            column_config={
                "date": st.column_config.DateColumn("Date", required=True),
                "kind": st.column_config.SelectboxColumn("Type", options=[item.value for item in CashFlowKind], required=True),
                "amount": st.column_config.NumberColumn("Amount (INR)", min_value=0.0, format="%.2f", required=True),
                "note": st.column_config.TextColumn("Source note", help="Optional capital-call, distribution, or valuation statement reference"),
            },
        )
    if st.button("Find product", key="search", type="secondary", disabled=not bool(query.strip())):
        st.session_state.report = None
        st.session_state.candidates, warning = find_candidates(TYPE_LABELS[product_label], query, provider)
        st.session_state.search_warning = warning
    if st.session_state.get("search_warning"):
        st.warning(st.session_state.search_warning)

    selected = None
    if st.session_state.candidates:
        labels = [f"{item.name} — {item.provider}" + (f" · {item.plan} {item.option}" if item.plan or item.option else "") for item in st.session_state.candidates]
        selected_label = st.selectbox("Confirm the exact product", labels, key="confirmed_product")
        selected = st.session_state.candidates[labels.index(selected_label)]
        benchmark = st.text_input("Benchmark", value=suggested_benchmark(selected), help="Suggested automatically; override it if the product discloses a different benchmark.")
    else:
        benchmark = ""
    ai_ready = load_ai() is not None
    st.caption("AI configured" if ai_ready else "AI not configured — deterministic evidence will still be shown")
    analyze = st.button("Analyze", key="analyze", type="primary", disabled=selected is None)

if analyze and selected:
    try:
        cash_flows = parse_cash_flow_rows(cash_flow_rows.to_dict("records")) if cash_flow_rows is not None else []
    except ValueError as exc:
        st.error(str(exc))
    else:
        with st.spinner("Collecting and validating evidence…"):
            st.session_state.report = FundAnalyzer(services()).analyze(AnalysisRequest(identity=selected, public_url=public_url.strip() or None, pdf_bytes=pdf.getvalue() if pdf else None, benchmark_override=benchmark.strip() or None, cash_flows=cash_flows))

if st.session_state.report:
    render_report(st.session_state.report)
