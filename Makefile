.PHONY: dev dev-real install

install:
\tpython -m pip install --upgrade pip
\tpip install -r requirements.txt || true
\tpip install dash plotly reportlab psycopg[binary] python-dotenv

dev:
\tUSE_SIM=1 python app.py

dev-real:
\tUSE_SIM=0 python app.py
