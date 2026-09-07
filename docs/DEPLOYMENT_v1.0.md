# HX//RACE v1.0 Deployment

## Core entry point

```text
app.py
```

## Core dependencies

Install:

```bash
pip install -r requirements.txt
```

Then run:

```bash
streamlit run app.py
```

## Optional CoolProp

The application has an internal property fallback.

CoolProp is therefore separated into:

```text
requirements-optional.txt
```

If your deployment platform supports it:

```bash
pip install -r requirements-optional.txt
```

If it does not, the application remains functional and labels the fallback property source.

## Environment

A modern supported Python 3.x release is required. The final repository is tested using the active execution environment recorded by the CI/test log.

## Streamlit deployment checklist

- repository root contains `app.py`
- repository root contains `requirements.txt`
- `.streamlit/config.toml` is committed
- deploy the `main` branch
- set the application entry file to `app.py`
- inspect deployment logs if dependency installation fails

## Security

Do not commit:

- passwords
- API keys
- proprietary thermodynamic parameters
- confidential process data

Interaction-parameter JSON files should contain only data you are permitted to store in the repository.

## Final smoke test

After deployment:

1. open the app
2. apply `Ethanol / Water Cooler`
3. confirm the live run produces positive duty and area
4. open Validation and confirm no software exception
5. generate the PDF report
6. download a project snapshot
7. reload the snapshot
