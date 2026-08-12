from __future__ import annotations

from datetime import datetime, timezone
import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from fund_analyzer.ai.client import AIClient
from fund_analyzer.config import AppConfig
from fund_analyzer.identity import rank_matches
from fund_analyzer.models import AnalysisStatus, EvidenceKind, ProductIdentity, ProductType
from fund_analyzer.orchestration import AnalysisRequest, FundAnalyzer, Services
from fund_analyzer.reporting import build_report_view
from fund_analyzer.sources.amfi import AmfiCollector
from fund_analyzer.sources.apmi import ApmiCollector
from fund_analyzer.sources.public_page import PublicPageCollector


TYPE_LABELS = {"Mutual Fund": ProductType.MUTUAL_FUND, "PMS": ProductType.PMS, "AIF": ProductType.AIF}


def load_ai():
    try:
        config = AppConfig.load(st.secrets)
        if config.api_key == "replace-locally":
            return None
        return AIClient(config)
    except Exception:
        return None


def services() -> Services:
    return Services(amfi=AmfiCollector(), apmi=ApmiCollector(), public_page=PublicPageCollector(), ai=load_ai())


def find_candidates(product_type: ProductType, query: str, provider: str) -> tuple[list[ProductIdentity], str | None]:
    try:
        if product_type is ProductType.MUTUAL_FUND:
            products = AmfiCollector().directory().products
            return [match.identity for match in rank_matches(query, products)[:12] if match.score >= 55], None
        if product_type is ProductType.PMS:
            rows = ApmiCollector().performance()
            products = [ProductIdentity(product_type=ProductType.PMS, name=row["approach"], provider=row["provider"]) for row in rows if row["approach"]]
            return [match.identity for match in rank_matches(query, products)[:12] if match.score >= 55], None
        if not provider.strip():
            return [], "Enter the AIF manager name so the uploaded factsheet can be identity-checked."
        return [ProductIdentity(product_type=ProductType.AIF, name=query.strip(), provider=provider.strip())], "SEBI registration should be verified from the factsheet or public URL."
    except Exception as exc:
        return [], f"Product directory unavailable: {type(exc).__name__}. Check your connection and try again."


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
        range_key = st.segmented_control("History", ["1Y", "3Y", "5Y", "Max"], default="Max", key="range")
        view = build_report_view(report, range_key or "Max")
        figure = go.Figure()
        figure.add_trace(go.Scatter(x=[point.date for point in view.chart.product], y=[point.value for point in view.chart.product], name="Product", line={"color": "#5B5CF6", "width": 2.5}))
        if view.chart.benchmark:
            figure.add_trace(go.Scatter(x=[point.date for point in view.chart.benchmark], y=[point.value for point in view.chart.benchmark], name="Benchmark", line={"color": "#94A3B8", "width": 2}))
        figure.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10), yaxis_title="Growth of ₹1 lakh", legend_orientation="h", hovermode="x unified")
        st.plotly_chart(figure, width="stretch")
    else:
        st.info("A NAV-style chart is not shown because the available evidence does not contain a defensible continuous performance series.")

    valid_metrics = [metric for metric in report.metrics if metric.value is not None]
    if valid_metrics:
        cols = st.columns(min(4, len(valid_metrics)))
        for index, metric in enumerate(valid_metrics):
            value = metric.value
            display = f"{value * 100:.2f}%" if metric.unit == "%" else f"{value:.2f}"
            cols[index % len(cols)].metric(metric.label, display)

    st.markdown("### Investment case")
    pros_col, cons_col = st.columns(2)
    with pros_col:
        st.markdown('<div class="case-card pros"><h4>PROS</h4>', unsafe_allow_html=True)
        if report.ai and report.ai.available:
            for item in report.ai.pros:
                st.markdown(f"- {badge('AI Assessment')} {html.escape(item.text)}", unsafe_allow_html=True)
        else:
            st.caption("Configure the AI endpoint to generate an independent assessment.")
        st.markdown("</div>", unsafe_allow_html=True)
    with cons_col:
        st.markdown('<div class="case-card cons"><h4>CONS</h4>', unsafe_allow_html=True)
        if report.ai and report.ai.available:
            for item in report.ai.cons:
                st.markdown(f"- {badge('AI Assessment', 'amber')} {html.escape(item.text)}", unsafe_allow_html=True)
        else:
            st.caption("No AI assessment is available; verified evidence remains below.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### 3–5 Year View")
    if report.ai and report.ai.available and report.ai.outlook:
        st.markdown(f"{badge('AI Assessment')} {html.escape(report.ai.outlook.text)}", unsafe_allow_html=True)
        with st.expander("Risks and conditions to monitor"):
            for item in [*report.ai.risks, *report.ai.monitoring]:
                st.markdown(f"- {html.escape(item.text)}")
    else:
        st.info("AI view unavailable. The report does not replace it with an invented conclusion.")

    if report.warnings:
        with st.expander("Data gaps and warnings", expanded=True):
            for warning in report.warnings:
                st.markdown(f"- {html.escape(warning)}")

    with st.expander(f"Evidence and sources ({len(report.evidence)})"):
        for item in report.evidence:
            label = "Verified Fact" if item.kind is EvidenceKind.VERIFIED_FACT else "Calculated Metric"
            link = f"[source]({item.source.url})" if item.source.url else item.source.title
            page = f", page {item.source.page}" if item.source.page else ""
            st.markdown(f"{badge(label)} **{html.escape(item.label)}:** {html.escape(str(item.value))} {html.escape(item.unit or '')}  \n{link} · observed {item.source.observed_at}{page} · retrieved {item.source.retrieved_at.date()}", unsafe_allow_html=True)

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
    product_label = left.selectbox("Product type", list(TYPE_LABELS), key="product_type")
    query = right.text_input("Product or strategy name", placeholder="e.g. Parag Parikh Flexi Cap Fund")
    provider = st.text_input("Manager / AMC (required for manual AIF lookup)", placeholder="e.g. Example Capital")
    public_url = st.text_input("Official website or factsheet URL (optional)", placeholder="https://...")
    pdf = st.file_uploader("Factsheet PDF (optional, text-based, max 15 MB)", type=["pdf"])
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
    with st.spinner("Collecting and validating evidence…"):
        st.session_state.report = FundAnalyzer(services()).analyze(AnalysisRequest(identity=selected, public_url=public_url.strip() or None, pdf_bytes=pdf.getvalue() if pdf else None, benchmark_override=benchmark.strip() or None))

if st.session_state.report:
    render_report(st.session_state.report)
