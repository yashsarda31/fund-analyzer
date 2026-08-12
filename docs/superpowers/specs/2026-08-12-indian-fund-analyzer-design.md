# Indian Fund Analyzer — Design Specification

**Date:** 2026-08-12  
**Status:** Approved design  
**Product type:** Standalone local Streamlit web app  
**Location:** `C:\Users\yashs\Downloads\fund-analyzer`

## 1. Purpose

Build a private research tool for evaluating one India-domiciled mutual fund, Portfolio Management Service (PMS) strategy, or Alternative Investment Fund (AIF) at a time. The tool fetches available public data, accepts an optional PDF factsheet, calculates dependable performance metrics locally, and uses a configurable MiniMax/Ollama-compatible AI endpoint for an independent 3–5 year investment assessment.

The output is an interactive on-screen report. It does not save analyses or export PDFs.

## 2. Product principles

1. Numeric facts must come from retrieved sources, uploaded documents, or deterministic calculations—not from AI generation.
2. The AI may make independent judgments, but each conclusion must cite the evidence item(s) it considered and must be labelled `AI Assessment`.
3. Every fact and metric must expose its source, observation date, and retrieval date.
4. Missing data must remain missing. The app must never estimate fund performance to fill gaps.
5. Fund-type differences matter. Mutual-fund NAV returns, PMS time-weighted returns, and AIF cash-flow returns must not be treated as interchangeable.
6. The app is research software, not investment advice.

## 3. Scope

### Included in version 1

- India-domiciled mutual funds, PMS strategies, and AIFs.
- One product per analysis.
- Product lookup by name.
- Direct website or factsheet URL input.
- One optional text-based PDF factsheet upload.
- Automatic benchmark selection with a user override.
- Interactive performance chart and metric cards when the source data supports them.
- AI-generated pros, cons, 3–5 year view, risks, and monitoring conditions.
- Evidence labels: `Verified Fact`, `Calculated Metric`, and `AI Assessment`.
- Source links, dates, freshness warnings, and missing-data disclosures.
- A one-click Windows launcher.

### Excluded from version 1

- Multi-product comparison.
- Scanned-PDF OCR.
- Excel or CSV upload.
- User accounts, cloud sync, saved reports, or analysis history.
- PDF/report export.
- Portfolio recommendations, allocation sizing, transactions, or adviser workflows.
- Paid data-vendor integrations.
- Deployment or public hosting.

## 4. User flow

1. The user selects `Mutual Fund`, `PMS`, or `AIF`.
2. The user searches by product name, pastes a public URL, or uses both.
3. The app returns matching official-directory records. The user confirms one product identity before analysis begins.
4. The user may add one PDF factsheet.
5. The app checks that the URL/PDF identity is consistent with the selected product and warns on ambiguity or mismatch.
6. The app fetches public evidence, parses the optional PDF, selects a likely benchmark, and lets the user override it.
7. Local calculations run first. The structured evidence packet is then sent to the configured AI endpoint.
8. The report renders. Refreshing or closing the session discards the report and uploaded PDF.

## 5. Architecture

The application is a Python package with a thin Streamlit interface and isolated service modules:

- `app.py`: page composition and session orchestration.
- `collectors/`: source-specific fetch and parse adapters.
- `identity/`: product normalization, matching, and mismatch detection.
- `documents/`: PDF text/table extraction and evidence mapping.
- `analytics/`: return, risk, benchmark, and coverage calculations.
- `ai/`: endpoint client, evidence-packet builder, response schema, and validation.
- `reporting/`: view models for charts, cards, pros/cons, warnings, and sources.
- `tests/fixtures/`: frozen representative source responses and PDF samples.

Each collector returns a common typed result containing observations, source metadata, warnings, and collection status. The UI never parses provider-specific responses directly.

## 6. Data sources and acquisition

The source hierarchy is:

1. Regulators and official industry bodies.
2. The AMC, PMS manager, or AIF manager's own disclosure.
3. The user-uploaded factsheet.
4. Other public pages used for discovery only, not as the sole source of numeric performance.

Primary connectors:

- **Mutual funds:** AMFI scheme directory and NAV history, plus official AMC documents/URLs.
- **PMS:** APMI investment-approach performance data, SEBI registration/disclosure records, and official manager documents/URLs.
- **AIF:** SEBI registration and aggregate disclosure data, official manager documents/URLs, and the uploaded factsheet.
- **Benchmarks:** official NSE Indices historical and total-return-index data when available; the product's disclosed benchmark takes priority.

The app stores fetched data only in memory for the active Streamlit session. Short retry/backoff is allowed during a request, but there is no cross-session cache in version 1.

## 7. Product identity resolution

Product names are normalized for case, punctuation, legal suffixes, plan/option labels, and common abbreviations. Matching uses exact identifiers where available, followed by conservative token similarity.

The app must ask for confirmation when multiple products remain plausible. It must not silently combine:

- Mutual-fund regular and direct plans.
- Growth and distribution options.
- Different PMS investment approaches from the same provider.
- Different AIF schemes, categories, or vintages under the same manager.

The uploaded PDF and pasted URL are checked against the selected name, manager, registration identifier, scheme/approach, and reporting date. A strong mismatch blocks document-derived facts until the user removes the document or selects the matching product.

## 8. PDF handling

Version 1 supports one text-based PDF factsheet. The parser extracts text and tables from the uploaded bytes without permanently writing the document to disk.

Extracted fields may include:

- Product identity and category.
- Inception/vintage date and benchmark.
- NAV, return, IRR, or multiple tables.
- AUM/corpus and portfolio holdings.
- Fees, performance fees, hurdle, high-water mark, exit load, lock-in, tenure, and minimum investment.
- Manager/team information and stated strategy.
- Risk disclosures and reporting date.

Every extracted item retains page number and a short supporting excerpt. The document is treated as untrusted data: embedded instructions are never followed. Unsupported encryption, image-only pages, low-confidence tables, or missing identity fields produce visible warnings rather than inferred values.

## 9. Performance and risk analytics

Calculations run only when observations are adequate and date-aligned. All annualized metrics disclose the period and frequency used.

### Mutual funds

- Absolute return for periods under one year.
- CAGR for 1, 3, 5 years and since inception where available.
- Growth of ₹1 lakh versus the selected benchmark.
- Annualized volatility, maximum drawdown, Sharpe, Sortino, downside capture, and benchmark alpha where history is sufficient.
- Rolling 1-year and 3-year return summaries when enough daily NAV data exists.

### PMS

- Display APMI-reported period returns and AUM as reported.
- Build a compounded performance series only from a complete sequence of compatible reported periodic returns.
- Calculate volatility, drawdown, Sharpe, Sortino, and alpha only when a sufficiently granular, continuous series is available.
- Clearly state that client-level PMS outcomes can differ because portfolios and cash flows may be customized.

### AIF

- Preserve the metrics actually appropriate to the product: IRR/XIRR, MOIC, TVPI, DPI, RVPI, and vintage-year comparison.
- Calculate XIRR or public-market-equivalent analysis only when dated contributions, distributions, and valuations are available.
- Do not translate an IRR snapshot into a NAV chart or CAGR.
- For products without a defensible series, show a cash-flow/valuation timeline or metric cards instead of an artificial performance line.

### Shared rules

- Use the product's officially disclosed benchmark when found; otherwise suggest a benchmark based on category and strategy and label the mapping as an AI assessment until the user confirms it.
- Align product and benchmark observations to common dates.
- Use the latest RBI-published 91-day Treasury-bill cut-off yield available on or before the report end date as the annualized risk-free rate. Show its value, observation date, and source; suppress risk-adjusted metrics if that evidence cannot be retrieved.
- Suppress any metric whose inputs fail minimum coverage, frequency, or freshness checks.

## 10. AI analysis

The AI client accepts a configurable base URL, API key, and model name from a local Streamlit secrets file. It targets an OpenAI-compatible chat-completions interface so the user's MiniMax/Ollama-compatible service can be configured without code changes.

The key is never printed, included in exception messages, or sent anywhere except the configured endpoint. The secrets file is excluded from version control. Analysis history is not persisted.

The model receives a bounded structured evidence packet containing:

- Product metadata.
- Verified facts with evidence IDs.
- Calculated metrics with formulas/input coverage.
- Portfolio, fee, liquidity, lock-in, team, and strategy evidence.
- Missing fields and explicit uncertainty.
- The user's 3–5 year horizon.

The model returns schema-validated JSON containing:

- Three to five pros.
- Three to five cons.
- A balanced 3–5 year assessment.
- Investor-fit considerations.
- Key risks and monitoring conditions.
- Evidence IDs for every conclusion.
- Confidence and limitations.

AI conclusions may synthesize and infer, but any number in the response must match the supplied evidence packet. Unsupported evidence references or changed numbers invalidate the AI response. The app retries once with a repair prompt; after that it renders the deterministic report with `AI analysis unavailable`.

## 11. Report interface

The Streamlit report uses a wide desktop layout inspired by the supplied reference image:

1. **Input panel:** product type, name search, URL, PDF upload, AI availability, and Analyze button.
2. **Identity header:** product name, manager, product type/category, registration identifier, inception/vintage, benchmark, reporting date, and status.
3. **Performance panel:** `1Y`, `3Y`, `5Y`, and `Max` range control; product/benchmark chart; metric cards; data-coverage note.
4. **Pros and cons:** two bordered columns with concise AI conclusions and expandable evidence.
5. **3–5 Year View:** balanced narrative, suitability considerations, liquidity/lock-in, fee drag, concentration, manager dependence, and monitoring conditions.
6. **Evidence and sources:** labelled facts/metrics/assessments, source links, document page references, freshness, retrieval timestamps, and gaps.
7. **Disclaimer:** past performance and model-generated analysis do not constitute investment advice.

When a fund type cannot support a NAV-like chart, the performance panel adapts rather than implying nonexistent precision.

## 12. Status and error model

Every analysis ends in one top-level status:

- `ANALYSIS COMPLETE`: enough verified information exists for the requested output.
- `ANALYSIS PARTIAL`: useful analysis exists, but named fields or periods are missing.
- `INSUFFICIENT VERIFIED DATA`: performance or identity evidence is too weak for a responsible analysis.
- `SOURCE UNAVAILABLE`: a required provider could not be reached after bounded retries.

Provider outages, invalid URLs, HTTP errors, ambiguous identities, stale data, incompatible benchmark periods, PDF extraction failures, and AI schema failures appear as specific, actionable warnings. A provider or AI failure must not erase already verified results from other sources.

## 13. Privacy and security

- The app binds to localhost by default.
- Only `http` and `https` public URLs are accepted; local-file and non-web schemes are rejected.
- URL downloads have size, content-type, redirect, and timeout limits.
- PDF size and page-count limits prevent accidental resource exhaustion.
- Uploaded bytes, fetched data, and reports are session-only.
- Secrets are loaded locally and redacted from UI/logging.
- Web and PDF text is handled as untrusted content and cannot override system instructions.

## 14. Testing strategy

### Unit tests

- CAGR, absolute return, annualized volatility, maximum drawdown, Sharpe, Sortino, alpha, rolling returns, XIRR, and private-market multiples.
- Date alignment, missing observations, plan/option separation, and minimum-coverage gates.
- Product-name normalization and ambiguity/mismatch detection.
- AI evidence-packet construction, JSON validation, numeric consistency, and evidence-reference validation.
- URL safety, secrets redaction, and document instruction isolation.

### Collector contract tests

- Frozen fixtures for representative AMFI, APMI, SEBI, NSE Indices, AMC/manager pages, and PDFs.
- Parser drift must fail visibly with a source-specific error instead of returning partial fields as complete.

### Integration tests

- Mutual fund with complete NAV and benchmark history.
- PMS with reported performance but insufficient daily history.
- AIF whose factsheet supplies cash-flow/private-market metrics.
- Ambiguous name, mismatched factsheet, stale document, provider outage, and malformed AI response.

### Smoke verification

- Automated Streamlit startup health check.
- One end-to-end sample analysis with network/AI calls mocked.
- Manual live-source checks against one product of each supported type before handoff.
- Windows launcher verification from a clean terminal.

## 15. Local operation

The project will provide:

- A Python virtual environment and pinned dependencies.
- A `.streamlit/secrets.toml.example` containing placeholder base URL, API key, and model fields.
- A one-click `run_fund_analyzer.bat` launcher that starts Streamlit on localhost and opens the browser.
- A concise README covering setup, secrets, launch, supported sources, limitations, and troubleshooting.

## 16. Acceptance criteria

Version 1 is complete when:

1. A user can find and confirm one Indian mutual fund, PMS strategy, or AIF by name and/or URL.
2. A user can upload one text-based PDF and see page-linked extracted evidence.
3. The tool produces accurate type-appropriate performance output without inventing missing history.
4. The report provides pros, cons, and a 3–5 year AI assessment whose evidence links validate.
5. The report visibly distinguishes verified facts, calculated metrics, and AI assessments.
6. Missing, stale, ambiguous, or unavailable data results in the defined non-success status rather than a misleading complete report.
7. Analyses and uploaded PDFs are not available after the session ends.
8. The configured secret is never exposed in UI, logs, tests, or source control.
9. Automated tests and the local Windows launcher pass before handoff.
