## Streamlit cockpit

HX//RACE also includes a Streamlit interface that calls the Python engineering engine directly.

```bash
pip install -r requirements.txt
streamlit run streamlit_app/app.py
```

The Streamlit layer is intentionally presentation-only: thermodynamics, heat-transfer correlations, hydraulics and optimisation remain inside the backend engineering modules.
