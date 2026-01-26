
# Unit Plan Reviewer (FHA / ANSI A117.1 Type A / Type B)

A Streamlit web app that reviews Revit-exported **vector PDF** unit plan sheets (floor plans, interior elevations, and door schedules when available) and generates accessibility review comments as:

- **Bluebeam-style issue list**
- **Grouped memo-style summaries**
- **Downloadable PDF report**
- **Simple review history** stored in SQLite (`reviews.db`)

> Note: This tool is intended as a **preliminary reviewer** that flags **likely issues** and “needs verification” items. It does not replace professional judgment or jurisdictional review.

---

## Features

- Upload **multi-sheet PDFs** (or single sheets)
- Select which pages to review
- Label pages: **Floor Plan**, **Interior Elevation**, **Door Schedule**, etc.
- Choose ruleset:
  - **FHA**
  - **ANSI A117.1 Type A**
  - **ANSI A117.1 Type B**
- Optional PDF text extraction to help with schedules/notes
- Generates:
  - On-screen findings
  - **PDF report download**
- Stores prior reviews in **SQLite** for quick retrieval
- Password gate + OpenAI API key stored in **Streamlit Secrets**

---

## Tech Stack

- **Streamlit** (UI + hosting)
- **PyMuPDF (fitz)** (PDF rendering + text extraction)
- **OpenAI API**
- **Pydantic** (structured JSON validation)
- **ReportLab** (PDF report generation)
- **SQLite** (history storage)

---

## Repository Structure

```
unit-plan-reviewer/
  app.py
  requirements.txt
  README.md
  .streamlit/
    config.toml
    secrets.toml.example
  src/
    auth.py
    pdf_utils.py
    llm_review.py
    report_pdf.py
    storage.py
    schemas.py
```

---

## Setup (Local)

### 1) Create a virtual environment (recommended)

**Windows (PowerShell):**
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Mac/Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

---

## Configure Secrets

Create `.streamlit/secrets.toml` (do not commit):

```toml
OPENAI_API_KEY = "sk-..."
APP_PASSWORD = "mySimplePassword123"
```

---

## Run the App

```bash
streamlit run app.py
```

---

## Deployment (Streamlit Cloud)

1. Push repo to GitHub
2. Create a new app in Streamlit Cloud
3. Set main file to `app.py`
4. Add secrets in Streamlit Cloud UI

---

## Disclaimer

This tool provides **assistance only** and does not replace professional or jurisdictional review.
