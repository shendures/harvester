# -*- coding: utf-8 -*-
"""
DB 연결 / 검증 / 읽기 / 저장 유틸리티

지원 DB: PostgreSQL, MySQL, MongoDB

[수정 이력]
- _check_db_table_exists : 커넥션/엔진 누수 수정, 오류 처리 추가
- read_db_data            : PostgreSQL engine dispose 추가,
                            MongoDB client finally 보장,
                            패스워드 URL 인코딩 적용
- save_db                 : data 빈 리스트 사전 검증,
                            MongoDB client.close() finally 보장,
                            PostgreSQL engine dispose finally 추가,
                            패스워드 URL 인코딩 전 함수 적용
- _build_sql_url          : 패스워드 특수문자 인코딩을 한 곳에서 처리하는
                            내부 헬퍼 신설 (중복 제거)
"""

import logging
import urllib.parse

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from sqlalchemy import (
    create_engine, MetaData, Table, Column, inspect,
    Integer, Float, Text, BigInteger, text,
)
from env import config

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════
#  내부 헬퍼
# ══════════════════════════════════════════════════════
def _build_sql_url(db_info: dict) -> str:
    """
    SQL 계열(PostgreSQL / MySQL) 연결 URL을 안전하게 조립합니다.

    [수정] 패스워드에 포함된 특수문자를 urllib.parse.quote_plus로 인코딩.
    기존 코드에서 _check_db_table_exists, read_db_data, save_db 각각
    raw 패스워드를 직접 URL에 삽입하던 문제를 이 헬퍼 한 곳에서 처리합니다.
    """
    driver = "mysql+pymysql" if db_info["db_env"] == "MySQL" else "postgresql"
    safe_pw = urllib.parse.quote_plus(str(db_info.get("password", "")))
    return (
        f'{driver}://{db_info["user"]}:{safe_pw}'
        f'@{db_info["host"]}:{db_info["port"]}/{db_info["database"]}'
    )


def _build_mongo_uri(db_info: dict) -> str:
    """
    MongoDB 연결 URI를 조립합니다.
    user / password 가 모두 있을 때만 인증 URI를 사용합니다.
    """
    user     = db_info.get("user", "").strip()
    password = db_info.get("password", "").strip()
    host     = db_info["host"]
    port     = db_info["port"]

    if user and password:
        safe_pw = urllib.parse.quote_plus(password)
        return f"mongodb://{user}:{safe_pw}@{host}:{port}/?authSource=admin"
    return f"mongodb://{host}:{port}/"


def _infer_col_type(value):
    """
    Python 값으로 SQLAlchemy 컬럼 타입을 추론합니다.
    PostgreSQL / MySQL save_db 양쪽에서 공통 사용합니다.
    """
    if isinstance(value, bool):   # bool은 int의 서브클래스이므로 먼저 체크
        return Integer
    if isinstance(value, int):
        return BigInteger if value > 2_147_483_647 else Integer
    if isinstance(value, float):
        return Float
    return Text


# ══════════════════════════════════════════════════════
#  공개 API
# ══════════════════════════════════════════════════════
def get_params(section: str) -> dict:
    """database.ini에서 섹션 파라미터 로드"""
    return config.config(section=section)


def _check_db_connect_info(db_info: dict) -> tuple[bool, str]:
    """
    실제 데이터베이스에 연결을 시도하여 정보가 유효한지 검증합니다.

    연결 조건:
        SQL 계열 (PostgreSQL, MySQL) : db_env, host, port, database, schema, user, password
        비SQL 계열 (MongoDB)          : db_env, host, port, database

    Returns:
        tuple[bool, str]: (성공 여부, 실패 원인 메시지)
                          성공 시 (True, ""), 실패 시 (False, "원인 설명")
    """
    db_env = db_info.get("db_env", "")

    # ── 지원 DB 타입 사전 검증 ──────────────────────────
    SUPPORTED_DB = ("PostgreSQL", "MySQL", "MongoDB")
    if db_env not in SUPPORTED_DB:
        return False, f"지원하지 않는 DB 타입입니다: '{db_env}' (지원: {', '.join(SUPPORTED_DB)})"

    # ── 필수 필드 사전 검증 ──────────────────────────────
    SQL_REQUIRED   = ["db_env", "host", "port", "database", "schema", "user", "password"]
    NOSQL_REQUIRED = ["db_env", "host", "port", "database"]
    required_fields = SQL_REQUIRED if db_env in ("PostgreSQL", "MySQL") else NOSQL_REQUIRED

    missing = [f for f in required_fields if not str(db_info.get(f, "")).strip()]
    if missing:
        label_map = {
            "db_env": "DB 타입", "host": "호스트", "port": "포트",
            "database": "DB명", "schema": "스키마", "user": "유저", "password": "비밀번호",
        }
        missing_labels = ", ".join(label_map.get(f, f) for f in missing)
        return False, f"필수 항목이 입력되지 않았습니다: {missing_labels}"

    try:
        # ── 1. MongoDB ────────────────────────────────────
        if db_env == "MongoDB":
            uri    = _build_mongo_uri(db_info)
            client = None
            try:
                client = MongoClient(uri, serverSelectionTimeoutMS=3000)
                client.admin.command("ping")
                db_list = client.list_database_names()
                if db_info["database"] in db_list:
                    return True, ""
                return False, f"데이터베이스 '{db_info.get('database')}'를 찾을 수 없습니다."
            finally:
                if client is not None:
                    client.close()

        # ── 2. PostgreSQL / MySQL ─────────────────────────
        else:
            # [수정] _build_sql_url 헬퍼로 패스워드 인코딩 통일
            tmp_url = _build_sql_url(db_info)
            connect_args = {"connect_timeout": 3}
            schema = db_info.get("schema", "").strip()
            if db_env == "PostgreSQL" and schema:
                connect_args["options"] = f'-csearch_path={schema}'

            tmp_engine = None
            try:
                tmp_engine = create_engine(tmp_url, pool_pre_ping=True, connect_args=connect_args)
                with tmp_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))

                    # ── 스키마 존재 검증 ──────────────────────
                    # search_path 세팅 자체는 잘못된 스키마여도 오류가 발생하지 않으므로
                    # information_schema를 직접 조회하여 스키마 존재 여부를 확인합니다.
                    if schema:
                        if db_env == "PostgreSQL":
                            row = conn.execute(
                                text(
                                    "SELECT 1 FROM information_schema.schemata "
                                    "WHERE schema_name = :s"
                                ),
                                {"s": schema},
                            ).fetchone()
                            if row is None:
                                return False, f"스키마 '{schema}'를 찾을 수 없습니다."

                        elif db_env == "MySQL":
                            # MySQL에서 스키마(SCHEMA)는 데이터베이스와 동일한 개념이므로
                            # SCHEMATA 테이블에서 SCHEMA_NAME으로 존재 여부를 확인합니다.
                            row = conn.execute(
                                text(
                                    "SELECT 1 FROM information_schema.SCHEMATA "
                                    "WHERE SCHEMA_NAME = :s"
                                ),
                                {"s": schema},
                            ).fetchone()
                            if row is None:
                                return False, f"스키마(데이터베이스) '{schema}'를 찾을 수 없습니다."

                return True, ""
            finally:
                if tmp_engine is not None:
                    tmp_engine.dispose()

    except OperationFailure:
        return False, f"데이터베이스 '{db_info.get('database')}'에 대한 접근 권한이 없습니다."

    except ConnectionFailure:
        return False, "서버 연결 실패 — 호스트 주소, 포트 번호, 혹은 방화벽 설정을 확인하세요."

    except Exception as e:
        err_msg = str(e)
        lower   = err_msg.lower()

        if any(k in lower for k in ("timeout", "timed out", "serverselectiontimeouterror")):
            reason = f"호스트({db_info.get('host')})에 연결할 수 없습니다. 호스트 주소 또는 포트를 확인하세요."
        elif any(k in lower for k in ("connection refused", "could not connect", "no route")):
            reason = f"연결이 거부되었습니다. 호스트({db_info.get('host')})와 포트({db_info.get('port')})를 확인하세요."
        elif any(k in lower for k in ("authentication", "access denied", "password", "login")):
            reason = "인증 실패 — 사용자 이름 또는 비밀번호를 확인하세요."
        elif any(k in lower for k in ("invalid schema", "search_path")):
            reason = f"스키마 '{db_info.get('schema')}'를 찾을 수 없습니다."
        elif any(k in lower for k in ("unknown database", "does not exist")):
            reason = f"데이터베이스 '{db_info.get('database')}'를 찾을 수 없습니다."
        elif "ssl" in lower:
            reason = "SSL/TLS 연결 오류가 발생했습니다. 보안 설정을 확인하세요."
        else:
            reason = err_msg

        return False, reason


def _check_db_table_exists(db_info: dict) -> bool:
    """
    지정한 테이블(컬렉션)이 DB에 존재하는지 확인합니다.

    Returns:
        bool: 존재하면 True, 없거나 연결 실패 시 False

    [수정]
    - MongoDB   : client를 finally에서 항상 close() (기존: 누수)
    - SQL 계열  : engine을 finally에서 항상 dispose() (기존: 누수)
    - 패스워드  : _build_sql_url 헬퍼로 특수문자 인코딩 (기존: raw 삽입)
    - 오류 처리 : try/except 추가 — 연결 실패 시 unhandled exception 방지 (기존: 없음)
    """
    db_env = db_info.get("db_env", "")

    try:
        # ── MongoDB ──────────────────────────────────────
        if db_env == "MongoDB":
            uri    = _build_mongo_uri(db_info)
            client = None
            try:
                client = MongoClient(uri, serverSelectionTimeoutMS=3000)
                collections = client[db_info["database"]].list_collection_names()
                return db_info["save_data_nm"] in collections
            finally:
                # [수정] 기존 코드는 finally 없어 커넥션 누수 발생
                if client is not None:
                    client.close()

        # ── PostgreSQL / MySQL ────────────────────────────
        else:
            # [수정] _build_sql_url 헬퍼로 패스워드 인코딩 통일 (기존: raw 삽입)
            tmp_url    = _build_sql_url(db_info)
            tmp_engine = None
            try:
                tmp_engine = create_engine(tmp_url, pool_pre_ping=True)
                schema = db_info.get("schema") if db_env == "PostgreSQL" else None
                return inspect(tmp_engine).has_table(db_info["save_data_nm"], schema=schema)
            finally:
                # [수정] 기존 코드는 finally 없어 엔진 누수 발생
                if tmp_engine is not None:
                    tmp_engine.dispose()

    except Exception as e:
        logger.error("[_check_db_table_exists] 테이블 존재 확인 실패 (%s): %s", db_env, e)
        return False


def read_db_data(db_info: dict, query: str) -> list[dict]:
    """
    DB에서 데이터를 읽어와 리스트 내 딕셔너리 형태로 반환합니다.

    Args:
        db_info (dict): DB 연결 정보
        query   (str) : PostgreSQL → SQL 쿼리문 / MongoDB → 컬렉션 이름

    Returns:
        list[dict]: 조회된 데이터 결과 리스트 (오류 시 빈 리스트)

    [수정]
    - PostgreSQL : engine을 finally에서 항상 dispose() (기존: 누수)
    - MongoDB    : client.close()를 finally로 이동 (기존: 예외 시 누수)
    - 패스워드   : _build_sql_url / _build_mongo_uri 헬퍼로 인코딩 통일
    """
    db_env      = db_info.get("db_env", "")
    result_data = []

    try:
        # ── 1. PostgreSQL ─────────────────────────────────
        if db_env == "PostgreSQL":
            connect_args = {}
            if db_info.get("schema"):
                connect_args["options"] = f"-csearch_path={db_info['schema']}"

            # [수정] _build_sql_url 헬퍼로 패스워드 인코딩 (기존: raw 삽입)
            engine = None
            try:
                engine = create_engine(
                    _build_sql_url(db_info),
                    connect_args=connect_args,
                    pool_pre_ping=True,
                )
                with engine.connect() as conn:
                    result = conn.execute(text(query))
                    keys   = result.keys()
                    result_data = [dict(zip(keys, row)) for row in result.fetchall()]
            finally:
                # [수정] 기존 코드는 engine.dispose() 없어 커넥션 풀 누수 발생
                if engine is not None:
                    engine.dispose()

        # ── 2. MySQL ──────────────────────────────────────
        elif db_env == "MySQL":
            engine = None
            try:
                engine = create_engine(
                    _build_sql_url(db_info),
                    pool_pre_ping=True,
                    connect_args={"charset": "utf8mb4"},
                )
                with engine.connect() as conn:
                    result = conn.execute(text(query))
                    keys   = result.keys()
                    result_data = [dict(zip(keys, row)) for row in result.fetchall()]
            finally:
                if engine is not None:
                    engine.dispose()

        # ── 3. MongoDB ────────────────────────────────────
        elif db_env == "MongoDB":
            # [수정] _build_mongo_uri 헬퍼로 패스워드 인코딩 통일
            client = None
            try:
                client = MongoClient(_build_mongo_uri(db_info), serverSelectionTimeoutMS=5000)
                db     = client[db_info["database"]]
                for doc in db[query].find({}):
                    doc.pop("_id", None)
                    result_data.append(doc)
            finally:
                # [수정] 기존 코드는 try 블록 내 client.close() → 예외 시 누수
                if client is not None:
                    client.close()

        else:
            logger.error("[read_db_data] 지원하지 않는 DB 환경입니다: %s", db_env)

    except Exception as e:
        logger.error("[read_db_data] DB 읽기 오류 발생 (%s): %s", db_env, e)

    return result_data


def save_db(db_info: dict, data: list[dict], mode: str = "append") -> None:
    """
    수집 데이터를 DB에 저장합니다.

    Args:
        db_info (dict)     : DB 연결 정보
        data    (list[dict]): 저장할 데이터
        mode    (str)      : "append" | "overwrite"

    Raises:
        ValueError  : data가 비어 있을 때
        RuntimeError: DB 저장 중 오류 발생 시 (원인 메시지 포함)

    [수정]
    - data 빈 리스트 사전 검증 추가 (기존: data[0] → IndexError)
    - MongoDB    : client.close()를 finally로 이동 (기존: 누수)
    - PostgreSQL : engine.dispose()를 finally로 추가 (기존: 누수)
    - MySQL      : 기존 finally 유지 (정상)
    - 패스워드   : _build_sql_url 헬퍼로 인코딩 통일 (기존: raw 삽입)
    """
    # [수정] data 빈 리스트 사전 검증 — 기존은 data[0]에서 IndexError 발생
    if not data:
        raise ValueError("[save_db] 저장할 데이터가 없습니다 (data가 빈 리스트).")

    db_env = db_info.get("db_env", "")

    # ── MongoDB ──────────────────────────────────────────
    if db_env == "MongoDB":
        # [수정] _build_mongo_uri 헬퍼로 패스워드 인코딩 통일
        client = None
        try:
            client    = MongoClient(_build_mongo_uri(db_info))
            connector = client.get_database(db_info["database"])

            if mode == "overwrite":
                connector.drop_collection(db_info["save_data_nm"])

            connector.get_collection(db_info["save_data_nm"]).insert_many(data)

        except Exception as e:
            raise RuntimeError(f"MongoDB DB 저장 중 오류 발생: {e}") from e
        finally:
            # [수정] 기존 코드는 client.close() 없어 커넥션 누수 발생
            if client is not None:
                client.close()

    # ── PostgreSQL ───────────────────────────────────────
    elif db_env == "PostgreSQL":
        engine = None
        try:
            # [수정] _build_sql_url 헬퍼로 패스워드 인코딩 통일 (기존: raw 삽입)
            engine = create_engine(
                _build_sql_url(db_info),
                connect_args={"options": f'-csearch_path={db_info["schema"]}'},
                pool_pre_ping=True,
            )

            sample  = data[0]
            columns = [Column(k, _infer_col_type(v)) for k, v in sample.items()]

            metadata      = MetaData()
            dynamic_table = Table(
                db_info["save_data_nm"],
                metadata,
                *columns,
                schema=db_info["schema"],
            )

            if mode == "overwrite":
                dynamic_table.drop(engine, checkfirst=True)

            metadata.create_all(engine)

            with engine.begin() as conn:
                conn.execute(dynamic_table.insert(), data)

        except Exception as e:
            raise RuntimeError(f"PostgreSQL DB 저장 중 오류 발생: {e}") from e
        finally:
            # [수정] 기존 코드는 finally 없어 엔진 누수 발생
            if engine is not None:
                engine.dispose()

    # ── MySQL ────────────────────────────────────────────
    elif db_env == "MySQL":
        engine = None
        try:
            # [수정] _build_sql_url 헬퍼로 패스워드 인코딩 통일 (기존: raw 삽입)
            engine = create_engine(
                _build_sql_url(db_info),
                pool_pre_ping=True,
                connect_args={"charset": "utf8mb4"},
            )

            sample  = data[0]
            columns = [Column(k, _infer_col_type(v)) for k, v in sample.items()]

            metadata      = MetaData()
            dynamic_table = Table(
                db_info["save_data_nm"],
                metadata,
                *columns,
            )

            if mode == "overwrite":
                dynamic_table.drop(engine, checkfirst=True)

            metadata.create_all(engine)

            with engine.begin() as conn:
                conn.execute(dynamic_table.insert(), data)

        except Exception as e:
            raise RuntimeError(f"MySQL DB 저장 중 오류 발생: {e}") from e
        finally:
            if engine is not None:
                engine.dispose()

    else:
        raise ValueError(f"[save_db] 지원하지 않는 DB 타입입니다: '{db_env}'")
