import logging
import os
from urllib.parse import urlsplit, urlunsplit, quote, unquote

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import URL
from config import Config

logger = logging.getLogger(__name__)
# Гарантируем вывод наших диагностик
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)


def _sanitize_database_url(raw_url: str) -> str:
    """Нормализует URL подключения к БД, процентизируя логин/пароль.
    Это устраняет ошибки декодирования в драйвере при нестандартных символах.
    """
    try:
        parts = urlsplit(raw_url)
        # parts.netloc может содержать: user:pass@host:port
        netloc = parts.netloc
        if "@" in netloc:
            creds, hostport = netloc.split("@", 1)
            if ":" in creds:
                user, password = creds.split(":", 1)
            else:
                user, password = creds, ""
            # Декодируем на случай уже процентизированных значений, затем кодируем заново
            user = quote(unquote(user), safe="") if user else ""
            password = quote(unquote(password), safe="") if password else ""
            if password:
                new_creds = f"{user}:{password}"
            else:
                new_creds = user
            netloc = f"{new_creds}@{hostport}"
            sanitized = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
            return sanitized
        return raw_url
    except Exception:
        # В случае любой ошибки возвращаем исходную строку, чтобы не блокировать запуск
        return raw_url


def _mask_url_for_log(db_url: str) -> str:
    try:
        parts = urlsplit(db_url)
        netloc = parts.netloc
        if "@" in netloc:
            creds, hostport = netloc.split("@", 1)
            if ":" in creds:
                user, password = creds.split(":", 1)
                if password:
                    password = "***"
                creds = f"{user}:{password}"
            # если без пароля
            netloc = f"{creds}@{hostport}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        return "<unable to mask db url>"


def _build_sqlalchemy_url(raw_url: str) -> str | URL:
    """Пытаемся собрать URL через SQLAlchemy URL.create для корректного экранирования.
    Возвращаем URL-объект, если разобрать удалось, иначе — процентизированную строку.
    """
    try:
        parts = urlsplit(raw_url)
        # user:pass@host:port
        username = None
        password = None
        host = None
        port = None
        if parts.netloc:
            hostpart = parts.netloc
            if "@" in hostpart:
                creds, hostport = hostpart.split("@", 1)
                if ":" in creds:
                    username, password = creds.split(":", 1)
                else:
                    username, password = creds, ""
            else:
                hostport = hostpart
            if hostport:
                if ":" in hostport:
                    host, port_str = hostport.rsplit(":", 1)
                    try:
                        port = int(port_str)
                    except Exception:
                        port = None
                else:
                    host = hostport
        database = parts.path[1:] if parts.path.startswith('/') else parts.path
        drivername = parts.scheme if parts.scheme else "postgresql+psycopg2"
        if drivername == "postgresql":
            drivername = "postgresql+psycopg2"
        return URL.create(
            drivername=drivername,
            username=username,
            password=password,
            host=host,
            port=port,
            database=database or None,
            query={}
        )
    except Exception:
        # fallback — процентизированная строка
        return _sanitize_database_url(raw_url)


# Создаем движок базы данных (с безопасной нормализацией URL)
_raw_db_url = Config.DATABASE_URL
_safe_db_url = _sanitize_database_url(_raw_db_url) if _raw_db_url else _raw_db_url
masked = _mask_url_for_log(_safe_db_url) if _safe_db_url else '<empty url>'
logger.info(f"Инициализация подключения к БД: {masked}")
try:
    logger.info(f"DATABASE_URL raw repr: {repr(_raw_db_url)}")
    if _raw_db_url:
        non_ascii = [(i, hex(ord(ch)), ch) for i, ch in enumerate(_raw_db_url) if ord(ch) > 127]
        if non_ascii:
            logger.warning(f"DATABASE_URL содержит не-ASCII символы: {non_ascii}")
except Exception:
    pass

sqlalchemy_url = _build_sqlalchemy_url(_safe_db_url) if _safe_db_url else _safe_db_url
print(f"[DB] sqlalchemy_url type: {type(sqlalchemy_url).__name__}, value: {sqlalchemy_url}")

# На Windows libpq читает файлы pgpass/service и может падать на декодировании.
# Отключим их чтение безопасно, чтобы исключить внешний шум.
try:
    if os.name == 'nt':
        os.environ.setdefault('PGPASSFILE', 'NUL')
        # Эти переменные отключают/переназначают сервис-файлы
        os.environ.pop('PGSERVICE', None)
        os.environ.pop('PGSERVICEFILE', None)
        os.environ.pop('PGSYSCONFDIR', None)
        logger.info("Windows: отключено чтение pgpass/service (PGPASSFILE=NUL)")
    # Логируем только имена переменных и безопасные значения
    pg_env = {k: v for k, v in os.environ.items() if k.startswith('PG')}
    logger.info(f"PG* env vars: { {k: ('<set>' if v else '') for k, v in pg_env.items()} }")
except Exception:
    pass

# Явно включаем utf8 кодировку на уровне параметров подключения и короткий таймаут
connect_args = {"options": "-c client_encoding=UTF8", "connect_timeout": 5}
engine = create_engine(
    sqlalchemy_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=1800,
)

# Создаем фабрику сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Импортируем модели для создания таблиц
from database.models import Base

# Создаем все таблицы с предварительным тестом соединения
def _test_db_connectivity() -> None:
    try:
        raw = engine.raw_connection()
        try:
            try:
                raw.set_client_encoding('UTF8')
                logger.info("DB: client_encoding установлен в UTF8 через psycopg2")
            except Exception:
                pass
            cur = raw.cursor()
            cur.execute("select version()")
            ver = cur.fetchone()[0]
            logger.info(f"DB: server version: {ver}")
            cur.execute("select 1")
            cur.fetchone()
            cur.close()
        finally:
            raw.close()
    except Exception:
        url_str = engine.url.render_as_string(hide_password=True)
        logger.exception(f"DB connectivity test failed for {url_str}")
        raise


def create_tables():
    _test_db_connectivity()
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        url_str = engine.url.render_as_string(hide_password=True)
        logger.exception(f"DB create_all failed for {url_str}")
        raise

