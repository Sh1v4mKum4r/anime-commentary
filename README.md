# anime-commentary

Automated short-form anime commentary pipeline. See `docs/superpowers/specs/` for the design.

## Quickstart (development)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env  # fill in values
python main.py --help
pytest
```

## Status

Foundation phase. Subsequent plans add the actual pipeline.
