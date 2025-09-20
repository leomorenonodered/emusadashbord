# db.py
import os
import psycopg
from contextlib import contextmanager

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DB   = os.getenv("PG_DB", "emusa")
PG_USER = os.getenv("PG_USER", "emusa")
PG_PASS = os.getenv("PG_PASS", "74087432")  # ajuste na empresa se for diferente

CONN_STR = f"host={PG_HOST} port={PG_PORT} dbname={PG_DB} user={PG_USER} password={PG_PASS}"

@contextmanager
def get_conn():
    with psycopg.connect(CONN_STR) as conn:
        yield conn

def init_schema():
    ddl = """
    CREATE TABLE IF NOT EXISTS leituras (
      id bigserial PRIMARY KEY,
      ts timestamptz NOT NULL DEFAULT now(),
      tensao_l1 double precision,
      tensao_l2 double precision,
      tensao_l3 double precision,
      tensao_ll_l1 double precision,
      tensao_ll_l2 double precision,
      tensao_ll_l3 double precision,
      tensao_ll_avg double precision,
      corrente_l1 double precision,
      corrente_l2 double precision,
      corrente_l3 double precision,
      potencia_kw_inst double precision,
      energia_kwh_a double precision,
      energia_kwh_b double precision,
      frequencia double precision,
      fp_avg double precision
    );
    CREATE INDEX IF NOT EXISTS idx_leituras_ts ON leituras(ts);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
            conn.commit()

def insert_leitura(d):
    sql = """
    INSERT INTO leituras
    (ts, tensao_l1, tensao_l2, tensao_l3,
     tensao_ll_l1, tensao_ll_l2, tensao_ll_l3, tensao_ll_avg,
     corrente_l1, corrente_l2, corrente_l3,
     potencia_kw_inst, energia_kwh_a, energia_kwh_b,
     frequencia, fp_avg)
    VALUES (to_timestamp(%(ts)s),
            %(tensao_l1)s, %(tensao_l2)s, %(tensao_l3)s,
            %(tensao_ll_l1)s, %(tensao_ll_l2)s, %(tensao_ll_l3)s, %(tensao_ll_avg)s,
            %(corrente_l1)s, %(corrente_l2)s, %(corrente_l3)s,
            %(potencia_kw_inst)s, %(energia_kwh_a)s, %(energia_kwh_b)s,
            %(frequencia)s, %(fp_avg)s)
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, d)
            conn.commit()

def export_csv_last_hours(hours=24):
    sql = f"""
    SELECT ts, tensao_l1, tensao_l2, tensao_l3,
           tensao_ll_l1, tensao_ll_l2, tensao_ll_l3, tensao_ll_avg,
           corrente_l1, corrente_l2, corrente_l3,
           potencia_kw_inst, energia_kwh_a, energia_kwh_b,
           frequencia, fp_avg
    FROM leituras
    WHERE ts >= now() - interval '{hours} hours'
    ORDER BY ts ASC
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [c[0] for c in cur.description]
            rows = cur.fetchall()
            return cols, rows

def select_last_hours(hours=24):
    sql = f"""
    SELECT ts, tensao_ll_avg, potencia_kw_inst, energia_kwh_a, frequencia, fp_avg
    FROM leituras
    WHERE ts >= now() - interval '{hours} hours'
    ORDER BY ts ASC
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
