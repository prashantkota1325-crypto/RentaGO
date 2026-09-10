"""
Database access layer for RentaGO Web.

Prefers the native `python-oracledb` driver (thin mode). Where that package is
not installed (or blocked by a network filter), it transparently falls back to a
SQL*Plus-backed driver that shells out to the `sqlplus` binary. This keeps the
app runnable in restricted environments while using the fast native driver when
available.
"""

import csv
import io
import os
import subprocess
import tempfile
from datetime import date, datetime

from .config import settings

SQLPLUS = os.environ.get(
    "RENTAGO_SQLPLUS",
    r"C:\oraclexe\dbhomeXE\bin\sqlplus.exe",
)

try:  # prefer native driver
    import oracledb as _oracledb
    HAS_NATIVE = True
except Exception:  # pragma: no cover - fallback path
    _oracledb = None
    HAS_NATIVE = False


# ---------------------------------------------------------------------------
# Value formatting for the sqlplus fallback
# ---------------------------------------------------------------------------
def _fmt(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return f"TO_TIMESTAMP('{value:%Y-%m-%d %H:%M:%S}','YYYY-MM-DD HH24:MI:SS')"
    if isinstance(value, date):
        return f"TO_DATE('{value:%Y-%m-%d}','YYYY-MM-DD')"
    s = str(value)
    # Newlines (especially BLANK lines) inside a literal terminate the
    # statement in SQL*Plus (SP2-0734), so multi-line values are emitted as
    # 'part' || CHR(10) || 'part' ... which keeps the script single-line and
    # still stores real line breaks in the column.
    if "\n" in s or "\r" in s:
        parts = s.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        return " || CHR(10) || ".join(
            "'" + p.replace("'", "''") + "'" for p in parts)
    return "'" + s.replace("'", "''") + "'"


def _substitute(sql: str, params):
    if not params:
        return sql
    if not isinstance(params, (list, tuple)):
        params = [params]
    # Oracle binds are :1, :2, ... Use unique sentinel tokens so that formatted
    # values (which may themselves contain colons, e.g. timestamps like
    # 14:16:50) can never be mistaken for a bind placeholder afterwards.
    sentinels = []
    for idx in range(len(params), 0, -1):
        token = f"\x00BIND{idx}\x00"
        sentinels.append((idx, token))
        sql = sql.replace(f":{idx}", token)
    for idx, token in sentinels:
        sql = sql.replace(token, _fmt(params[idx - 1]))
    return sql


# ---------------------------------------------------------------------------
# SQL*Plus fallback driver
# ---------------------------------------------------------------------------
class _SqlplusCursor:
    def __init__(self, conn):
        self._conn = conn
        self._rows = []
        self._desc = []
        self.description = []
        self.rowcount = 0
        self._pos = 0

    def execute(self, sql, params=None):
        sql = _substitute(sql, params)
        self._rows, self._desc, self.rowcount = self._conn._run(sql)
        self.description = self._desc
        self._pos = 0
        return self

    def fetchone(self):
        if self._pos < len(self._rows):
            row = self._rows[self._pos]
            self._pos += 1
            return tuple(row)
        return None

    def fetchall(self):
        out = [tuple(r) for r in self._rows[self._pos:]]
        self._pos = len(self._rows)
        return out


class _SqlplusConnection:
    def __init__(self):
        self._user = settings.DB_USER
        self._pwd = settings.DB_PASSWORD
        self._connect_pwd = '"' + self._pwd.replace('"', '""') + '"'
        self._dsn = f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_SERVICE}"
        if not os.path.exists(SQLPLUS):
            raise RuntimeError(
                f"sqlplus not found at {SQLPLUS}. Install python-oracledb or set RENTAGO_SQLPLUS."
            )

    def _run_raw(self, script: str):
        # Self-contained TNS_ADMIN enabling EZCONNECT (has no tnsnames dependency).
        tns = argparse_tnsadmin()
        lines = [
            f"CONNECT {self._user}/{self._connect_pwd}@//{self._dsn}",
            "SET DEFINE OFF",
            "SET PAGESIZE 0",
            "SET LONG 100000",
            "SET LONGCHUNKSIZE 100000",
            "SET FEEDBACK OFF",
            "SET HEADING ON",
            "SET MARKUP CSV ON QUOTE ON",
            script,
            "SET MARKUP CSV OFF",
            "EXIT;",
        ]
        fd, path = _temp_script("\n".join(lines))
        try:
            proc = subprocess.run(
                [SQLPLUS, "-S", "-L", "/nolog", f"@{path}"],
                capture_output=True, timeout=120,
                env=_sqlplus_env(tns),
            )
        finally:
            _remove(path)
        out = None
        for enc in ("utf-8", "cp1252"):
            try:
                out = (proc.stdout or b"").decode(enc) + (proc.stderr or b"").decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if out is None:
            out = (proc.stdout or b"").decode("utf-8", "replace") + \
                  (proc.stderr or b"").decode("utf-8", "replace")
        err = _db_error(out)
        if err:
            raise RuntimeError(f"SQL*Plus error: {err}")
        return out

    def _run(self, sql):
        out = self._run_raw(sql.replace('\r', '').rstrip().rstrip(';') + ";")
        return _parse_csv(out)

    def multi_run(self, statements):
        """Run several (already substituted) SELECTs in ONE sqlplus spawn.

        Statements are interleaved with marker selects
        (`SELECT '##RSn##' AS M FROM DUAL`) so the CSV output can be split
        back into per-statement blocks.
        """
        parts = []
        for i, stmt in enumerate(statements, start=1):
            parts.append(stmt.replace('\r', '').rstrip().rstrip(';') + ";")
            parts.append(f"SELECT '##RS{i}##' AS M FROM DUAL;")
        out = self._run_raw("\n".join(parts))
        return _parse_blocks(out, len(statements))

    def cursor(self):
        return _SqlplusCursor(self)

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


def _temp_script(content):
    fd, path = tempfile.mkstemp(suffix=".sql", prefix="rentago_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return fd, path


def argparse_tnsadmin():
    """Create (once) a self-contained TNS_ADMIN dir that enables EZCONNECT."""
    tns = os.path.join(tempfile.gettempdir(), "rentago_tns")
    os.makedirs(tns, exist_ok=True)
    sqlnet = os.path.join(tns, "sqlnet.ora")
    if not os.path.exists(sqlnet):
        with open(sqlnet, "w", encoding="utf-8") as f:
            f.write("SQLNET.AUTHENTICATION_SERVICES= (NTS)\nNAMES.DIRECTORY_PATH= (TNSNAMES, EZCONNECT)\n")
    return tns


def _sqlplus_env(tns):
    env = dict(os.environ)
    env["TNS_ADMIN"] = tns
    return env


def _remove(path):
    try:
        os.remove(path)
    except Exception:
        pass


def _parse_csv(text):
    """Parse SQL*Plus CSV MARKUP output into (rows, description, rowcount)."""
    text = text.replace("\x00", "").strip()
    if not text:
        return [], [], 0
    lines = [ln for ln in text.splitlines() if ln.strip()]
    # Headers come first (CSV header row), then data rows.
    header = lines[0]
    data = lines[1:]
    parsed = list(csv.reader(io.StringIO("\n".join([header] + data))))
    if not parsed:
        return [], [], 0
    desc = [(c.strip(), None, None, None, None, None, None) for c in parsed[0]]
    rows = parsed[1:]
    return rows, desc, len(rows)


def _parse_blocks(text, count):
    """Split multi-statement CSV output into per-statement (headers, rows)."""
    text = text.replace("\x00", "").strip()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    blocks = []
    header = None
    rows = []
    for ln in lines:
        try:
            vals = next(csv.reader([ln]))
        except (csv.Error, StopIteration):
            continue
        if len(vals) == 1 and vals[0].startswith("##RS") and vals[0].endswith("##"):
            if rows and rows[-1] == ["M"]:
                rows.pop()  # drop the marker select's own header line
            blocks.append((header or [], rows))
            header, rows = None, []
            continue
        if header is None:
            header = [v.strip() for v in vals]
        else:
            rows.append(vals)
    if header is not None:
        if rows and rows[-1] == ["M"]:
            rows.pop()
        blocks.append((header, rows))
    while len(blocks) < count:
        blocks.append(([], []))
    return blocks[:count]


def _db_error(text):
    """Return the first SQL*Plus/Oracle error line, or None."""
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("ORA-") or s.startswith("PLS-") or s.startswith("SP2-"):
            return s
    return None


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------
def get_connection():
    """Return a DB connection (native oracledb thin mode, or sqlplus fallback)."""
    if HAS_NATIVE:
        # Thin mode needs no Oracle client libraries and no init call.
        return _oracledb.connect(
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            dsn=settings.dsn,
        )
    return _SqlplusConnection()


def multi_fetch(conn, pairs):
    """Run several SELECTs and return [(headers, rows), ...].

    `pairs` is a list of (sql, params-or-None). On the sqlplus fallback all
    statements run in ONE subprocess spawn (a huge win when each spawn costs
    ~0.5-1s); on the native driver they run sequentially on one cursor.
    Headers are lower-cased column names.
    """
    if isinstance(conn, _SqlplusConnection):
        stmts = [_substitute(sql, params) for sql, params in pairs]
        blocks = conn.multi_run(stmts)
        return [([h.lower() for h in headers], rows) for headers, rows in blocks]
    out = []
    cur = conn.cursor()
    for sql, params in pairs:
        cur.execute(sql, params or None)
        headers = [d[0].lower() for d in cur.description]
        out.append((headers, [list(r) for r in cur.fetchall()]))
    return out


def get_admin_connection():
    """Connect as an admin/DBA user to bootstrap the schema (native only)."""
    if not HAS_NATIVE:
        raise RuntimeError("Native oracledb required for admin connection.")
    user = os.environ.get("RENTAGO_ADMIN_USER", "SYSTEM")
    pwd = os.environ.get("RENTAGO_ADMIN_PASSWORD", "oracle")
    return _oracledb.connect(user=user, password=pwd, dsn=settings.admin_dsn)


def run_script(sql_text, connection=None):
    """Execute a multi-statement DDL/DML script."""
    conn = connection or get_connection()
    if isinstance(conn, _SqlplusConnection):
        # Run raw multi-statement script via sqlplus.
        cpwd = '"' + settings.DB_PASSWORD.replace('"', '""') + '"'
        lines = [
            f"CONNECT {settings.DB_USER}/{cpwd}@//{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_SERVICE}",
            "SET DEFINE OFF",
            "WHENEVER SQLERROR CONTINUE",
            sql_text,
            "EXIT;",
        ]
        fd, path = _temp_script("\n".join(lines))
        try:
            subprocess.run([SQLPLUS, "-S", "-L", "/nolog", f"@{path}"],
                           capture_output=True, timeout=600,
                           env=_sqlplus_env(argparse_tnsadmin()))
        finally:
            _remove(path)
        return
    cur = conn.cursor()
    stmts = [s.strip() for s in sql_text.replace("\n", " ").split(";") if s.strip()]
    for stmt in stmts:
        try:
            cur.execute(stmt)
        except Exception as e:
            print(f"  [warn] statement skipped: {e}")
    conn.commit()
