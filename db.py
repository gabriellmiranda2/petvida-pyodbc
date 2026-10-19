import os
from contextlib import contextmanager
import pyodbc


def montar_connection_string() -> str:
    server = os.environ["PETVIDA_SERVER"]
    db = os.environ["PETVIDA_DB"]
    user = os.environ.get("PETVIDA_USER")
    pwd = os.environ.get("PETVIDA_PASSWORD")
    base = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={server};Database={db};"
        "Encrypt=yes;TrustServerCertificate=yes;"
    )
    if user:  # autenticação SQL
        return base + f"UID={user};PWD={pwd};"
    return base + "Trusted_Connection=yes;"  # autenticação Windows


def conectar() -> pyodbc.Connection:
    return pyodbc.connect(montar_connection_string(), autocommit=False)


@contextmanager
def transacao():
    conn = conectar()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def testar_conexao() -> dict:
    with transacao() as cur:
        cur.execute(
            "SELECT @@SERVERNAME AS servidor, DB_NAME() AS banco, @@VERSION AS versao"
        )
        r = cur.fetchone()
        return {"servidor": r.servidor, "banco": r.banco, "versao": r.versao}
