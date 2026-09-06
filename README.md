# Indian Fund Analyzer

A private, session-only research tool for one Indian mutual fund, PMS strategy, or AIF at a time. It combines sourced public data, an optional PDF factsheet, deterministic calculations, and an evidence-linked AI assessment.

The app runs only on `127.0.0.1`. It does not save uploaded PDFs or completed analyses.

## First-time setup

Install 64-bit Python 3.11, then open PowerShell in this folder and run:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
```

Edit `.streamlit\secrets.toml` with your endpoint:

```toml
[ai]
base_url = "http://127.0.0.1:11434/v1"
api_key = "your-key"
model = "minimax-m3"
```

The endpoint must expose an OpenAI-compatible `/chat/completions` API. For a local Ollama-compatible server that does not require authentication, use any non-empty placeholder key accepted by that server. The real secrets file is excluded from Git and the key is redacted from application errors.

## Run

Double-click `run_fund_analyzer.bat`, or run:

```powershell
.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

The browser opens at `http://127.0.0.1:8501`.

## Workflow

1. Select Mutual Fund, PMS, or AIF.
2. Search by product/strategy name. For an AIF, also enter the manager.
3. Confirm the exact product. Direct/regular and growth/distribution plans remain separate.
4. Optionally add an official public URL and one text-based or scanned PDF factsheet.
5. For an AIF, add dated contribution, distribution, and terminal residual-value rows. Enter positive amounts; the event type controls the sign.
6. Check or override the suggested benchmark.
7. Select **Analyze**.

The report shows performance only when a defensible series exists. It labels content as a verified fact, calculated metric, or AI assessment and preserves dates and source links.

## Status meanings

- **ANALYSIS COMPLETE:** identity, usable performance evidence, and the selected benchmark context are present.
- **ANALYSIS PARTIAL:** useful evidence exists, but one or more material fields or comparisons are missing.
- **INSUFFICIENT VERIFIED DATA:** the app cannot defend a performance conclusion from available evidence.
- **SOURCE UNAVAILABLE:** required public evidence could not be reached or parsed.

## Sources and limitations

- Mutual-fund identity and latest NAV data originate with AMFI. Long NAV history is retrieved from the public MFAPI service, which republishes AMFI records; the report discloses this intermediary.
- PMS performance is read from APMI's investment-approach table. `NA` remains missing and is never converted to zero.
- SEBI registration/disclosure records establish identity and regulatory context, not scheme-level AIF performance.
- AIF analysis usually needs a dated manager factsheet. XIRR, TVPI, DPI, and RVPI are calculated only from structured user-entered cash flows and are not converted into NAV or CAGR.
- XIRR uses actual dates. TVPI is `(distributions + residual value) / contributions`; DPI is `distributions / contributions`; RVPI is `residual value / contributions`.
- AIF input requires exactly one residual-value row, dated no earlier than every contribution or distribution. Enter zero explicitly for a fully realized fund.
- NSE TRI and RBI parser modules enforce official data shapes, but a missing or changed upstream service is shown as unavailable rather than silently substituted.
- PDFs must be no more than 15 MB and 150 pages and match the confirmed product. Sparse or image-only pages use local English OCR for up to 50 pages.
- OCR never sends a page to a cloud service. OCR-derived fields are marked as lower-confidence document extracts and must be checked against the original scan.
- Public sources can change markup or restrict automated access. Such failures produce explicit warnings.
- AI may make independent judgments but cannot alter supplied numbers; each conclusion must cite evidence IDs. Invalid model output is rejected.

## Privacy

- No user account, database, report history, cloud sync, analytics, or export.
- Uploaded PDF bytes and report objects live only in the current Streamlit session.
- Public URLs reject local, private, link-local, reserved, credential-bearing, and non-HTTP(S) targets.
- Web pages and PDFs are treated as untrusted data and cannot override AI rules.

## Local OCR setup

This workspace already has the English OCR language model under the ignored `.tools` directory. On a fresh checkout, install Tesseract OCR with:

```powershell
winget install --id UB-Mannheim.TesseractOCR --exact
```

PyMuPDF looks for English language data in the project-local `.tools\Tesseract-OCR\tessdata`, the standard Windows installation folder, and the current user's local-programs folder. If it cannot find `eng.traineddata`, scanned PDFs remain private but the report shows an explicit local-OCR-unavailable warning.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

## Troubleshooting

- **No products found:** simplify the query and confirm internet access.
- **AI not configured:** copy the example secrets file and check the base URL, key, and model.
- **PDF mismatch:** confirm the selected scheme/strategy and upload its own latest factsheet. Check OCR spellings on low-quality scans.
- **No chart for an AIF:** provide contributions, distributions, and one latest residual value. Snapshot factsheet multiples do not create a cash-flow timeline.
- **Source unavailable:** retry later. The app will not invent a replacement value.

## Disclaimer

This is a research tool, not investment advice. Past performance may not be sustained. Source data and AI assessments can be incomplete or wrong; verify important conclusions with original documents and a qualified adviser.
