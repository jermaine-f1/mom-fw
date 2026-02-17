# Risk Control TA

A FastAPI-based web application for technical analysis risk control.

## Setup

```bash
pip install -e ".[dev]"
```

## Run

```bash
uvicorn risk_control_ta.main:app --reload
```

## Test

```bash
pytest
```

## Lint

```bash
ruff check .
ruff format --check .
```
