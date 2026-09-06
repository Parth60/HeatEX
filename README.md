# Streamlit UI

This folder is the Streamlit interface for HX//RACE.

It expects the existing project layout to contain:

```text
backend/
  app/
streamlit_app/
  app.py
```

From the repository root:

```bash
pip install -r requirements.txt
streamlit run streamlit_app/app.py
```

The app imports the engineering engine directly from `backend/app`, so equations stay out of the UI layer.
