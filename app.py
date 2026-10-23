import asyncio
import ast
import codecs
import json
import logging
import os
import re
import shlex
import shutil
import signal
import sqlite3
import sys
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask


def _application_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIRECTORY = _application_directory()
RESOURCE_DIRECTORY = Path(getattr(sys, "_MEIPASS", APP_DIRECTORY)).resolve()
CONFIG_PATH = APP_DIRECTORY / "app_config.json"


@dataclass(frozen=True)
class ApplicationConfig:
    ip_address: str
    port: int
    report_directory: Path
    log_directory: Path
    test_directory: Path
    database_path: Path


def _load_application_config() -> ApplicationConfig:
    try:
        with CONFIG_PATH.open(encoding="utf-8") as config_file:
            raw_config = json.load(config_file)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not load application configuration from {CONFIG_PATH}: {error}") from error

    if not isinstance(raw_config, dict):
        raise RuntimeError(f"Application configuration must be a JSON object: {CONFIG_PATH}")

    ip_address = raw_config.get("ip_address")
    if not isinstance(ip_address, str) or not ip_address.strip():
        raise RuntimeError("app_config.json must define a non-empty string 'ip_address'.")

    port = raw_config.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise RuntimeError("app_config.json must define 'port' as an integer between 1 and 65535.")

    def configured_path(key: str) -> Path:
        value = raw_config.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"app_config.json must define a non-empty string '{key}'.")
        path = Path(value)
        return (path if path.is_absolute() else APP_DIRECTORY / path).resolve()

    return ApplicationConfig(
        ip_address=ip_address.strip(),
        port=port,
        report_directory=configured_path("report_path"),
        log_directory=configured_path("log_path"),
        test_directory=configured_path("test_path"),
        database_path=configured_path("sqlite_db_path"),
    )


APP_CONFIG = _load_application_config()
TESTS_DIRECTORY = APP_CONFIG.test_directory
STATIC_DIRECTORY = RESOURCE_DIRECTORY / "static"
TEMP_DIRECTORY = APP_DIRECTORY / "tmp"
REPORTS_DIRECTORY = APP_CONFIG.report_directory
LOG_DIRECTORY = APP_CONFIG.log_directory
DATABASE_PATH = APP_CONFIG.database_path

for directory in (
    TEMP_DIRECTORY,
    REPORTS_DIRECTORY,
    LOG_DIRECTORY,
    DATABASE_PATH.parent,
):
    directory.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("robot_workspace")
logger.setLevel(logging.INFO)
if not any(
    isinstance(handler, logging.FileHandler)
    and Path(handler.baseFilename) == (LOG_DIRECTORY / "application.log").resolve()
    for handler in logger.handlers
):
    file_handler = logging.FileHandler(LOG_DIRECTORY / "application.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(file_handler)
logger.propagate = False
logger.info("Application configuration loaded from %s", CONFIG_PATH)

app = FastAPI(title="Test Directory Navigator")
app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")
app.mount("/reports", StaticFiles(directory=REPORTS_DIRECTORY), name="reports")

RUNS: dict[str, dict[str, object]] = {}
RUN_TASKS: dict[str, asyncio.Task[None]] = {}
RUN_PROCESSES: dict[str, asyncio.subprocess.Process] = {}
RUN_OUTPUT_SOCKETS: dict[str, set[WebSocket]] = {}
RUN_OUTPUT_LOCKS: dict[str, asyncio.Lock] = {}
MAX_RUN_OUTPUT_CHARS = 262_144


def _database_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def _initialize_run_database() -> None:
    with _database_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                report_name TEXT NOT NULL,
                directory TEXT NOT NULL,
                status TEXT NOT NULL,
                command TEXT NOT NULL,
                process_id INTEGER,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                exit_code INTEGER,
                message TEXT NOT NULL,
                console_output TEXT NOT NULL DEFAULT '',
                progress_current INTEGER NOT NULL DEFAULT 0,
                progress_total INTEGER NOT NULL DEFAULT 0,
                report_url TEXT,
                log_url TEXT,
                output_url TEXT
            )
            """
        )
        connection.execute("PRAGMA journal_mode=WAL")


def _load_persisted_runs() -> None:
    with _database_connection() as connection:
        rows = connection.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
        for row in rows:
            run = dict(row)
            run["console_output_truncated"] = len(str(run["console_output"])) > MAX_RUN_OUTPUT_CHARS
            run["report_file"] = str(
                REPORTS_DIRECTORY
                / str(run["report_name"])
                / f"{run['report_name']}_report.html"
            )
            if run["status"] in {"queued", "running"}:
                run["status"] = "interrupted"
                run["message"] = (
                    "The server restarted while this run was active. "
                    "Its saved output is available; start a new run to continue."
                )
                run["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
                connection.execute(
                    "UPDATE runs SET status = ?, message = ?, finished_at = ? WHERE id = ?",
                    (run["status"], run["message"], run["finished_at"], run["id"]),
                )
            RUNS[str(run["id"])] = run


def _persist_run_state(run: dict[str, object]) -> None:
    with _database_connection() as connection:
        connection.execute(
            """
            UPDATE runs
            SET status = ?, process_id = ?, started_at = ?, finished_at = ?,
                exit_code = ?, message = ?, progress_current = ?, progress_total = ?,
                report_url = ?, log_url = ?, output_url = ?
            WHERE id = ?
            """,
            (
                run["status"], run.get("process_id"), run.get("started_at"),
                run.get("finished_at"), run.get("exit_code"), run["message"],
                run.get("progress_current", 0), run.get("progress_total", 0),
                run.get("report_url"), run.get("log_url"), run.get("output_url"),
                run["id"],
            ),
        )


_initialize_run_database()
_load_persisted_runs()


class RobotTestCase(BaseModel):
    name: str
    documentation: str
    tags: list[str] = Field(default_factory=list)


class RobotFile(BaseModel):
    name: str
    display_name: str
    test_cases: list[RobotTestCase]


class RobotVariableField(BaseModel):
    key: str | None = None
    value: str
    value_type: Literal["string", "integer", "float", "boolean", "none"] = "string"
    expression: bool = False


class RobotVariable(BaseModel):
    name: str
    kind: Literal["scalar", "dictionary", "list", "set", "tuple"]
    expression: bool = False
    composed_from: list[str] = Field(default_factory=list)
    fields: list[RobotVariableField] = Field(max_length=1000)


class RobotVariablesUpdate(BaseModel):
    variables: list[RobotVariable] = Field(max_length=1000)


class UndefinedRobotVariable(BaseModel):
    name: str
    type_hint: Literal[
        "scalar", "string", "integer", "float", "boolean", "none",
        "list", "set", "tuple", "dictionary",
    ]
    suggested_value: str | None = None


class RobotRunFile(BaseModel):
    name: str
    tests: list[str] = Field(min_length=1, max_length=1000)


class RobotRunRequest(BaseModel):
    directory: str
    files: list[RobotRunFile] = Field(min_length=1, max_length=100)
    variables: list[RobotVariable] = Field(max_length=1000)
    predefined_variables: list[RobotVariable] = Field(default_factory=list, max_length=1000)
    include_tags: list[str] = Field(default_factory=list, max_length=100)
    exclude_tags: list[str] = Field(default_factory=list, max_length=100)
    report_name: str | None = Field(default=None, max_length=200)


class RobotReportMergeRequest(BaseModel):
    report_names: list[str] = Field(min_length=2, max_length=100)
    report_name: str = Field(min_length=1, max_length=100)


class RobotReportSelection(BaseModel):
    report_names: list[str] = Field(min_length=1, max_length=100)


@dataclass(frozen=True)
class RobotRunPaths:
    variable_file: Path
    modifier_file: Path
    output_file: Path
    log_file: Path
    report_file: Path
    progress_listener: Path


@dataclass(frozen=True)
class PreparedRobotRun:
    report_name: str
    command: list[str]
    paths: RobotRunPaths


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIRECTORY / "html" / "index.html")


@app.get("/tests-status")
async def tests_status_page() -> FileResponse:
    return FileResponse(STATIC_DIRECTORY / "html" / "tests_status.html")


@app.get("/test-reports")
async def test_reports_page() -> FileResponse:
    return FileResponse(STATIC_DIRECTORY / "html" / "test_reports.html")


@app.get("/api/directories", response_model=list[str])
async def list_test_directories() -> list[str]:
    try:
        return sorted(
            directory.name
            for directory in TESTS_DIRECTORY.iterdir()
            if directory.is_dir() and directory.name != "libraries"
        )
    except OSError as error:
        raise HTTPException(
            status_code=500,
            detail="Unable to read the test directory.",
        ) from error


def _read_test_cases(robot_file: Path) -> list[RobotTestCase]:
    test_cases: list[RobotTestCase] = []
    in_test_section = False
    current_test: RobotTestCase | None = None
    current_setting: str | None = None

    for line in robot_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("***") and stripped.endswith("***"):
            in_test_section = stripped.casefold() in {
                "*** test cases ***",
                "*** tasks ***",
            }
            current_test = None
            current_setting = None
            continue

        if not in_test_section or not stripped or stripped.startswith("#"):
            continue

        if not line[0].isspace():
            current_test = RobotTestCase(name=stripped, documentation="")
            test_cases.append(current_test)
            current_setting = None
            continue

        if current_test is None:
            continue

        if stripped.startswith("..."):
            continuation = stripped[3:].strip()
            if current_setting == "documentation" and continuation:
                current_test.documentation = " ".join(
                    part for part in (current_test.documentation, continuation) if part
                )
            elif current_setting == "tags" and continuation:
                current_test.tags.extend(continuation.split())
            continue

        setting = re.match(r"\[Documentation\]\s{2,}(.*)", stripped, re.IGNORECASE)
        if setting:
            current_test.documentation = setting.group(1).strip()
            current_setting = "documentation"
            continue

        tags = re.match(r"\[Tags\](?:\s{2,}(.*))?$", stripped, re.IGNORECASE)
        if tags:
            current_test.tags.extend((tags.group(1) or "").split())
            current_setting = "tags"
            continue

        current_setting = None

    for test_case in test_cases:
        test_case.tags = list(dict.fromkeys(test_case.tags))

    return test_cases


def _section_directory(directory_name: str) -> Path:
    directory = TESTS_DIRECTORY / directory_name
    if (
        directory_name in {".", ".."}
        or Path(directory_name).name != directory_name
        or not directory.is_dir()
        or directory.resolve().parent != TESTS_DIRECTORY.resolve()
    ):
        raise HTTPException(status_code=404, detail="Test directory not found.")
    return directory


def _normalized_variable_name(name: str) -> str:
    match = re.fullmatch(r"[$@&%]\{([^}]+)\}", name)
    value = match.group(1) if match else name
    return re.sub(r"[\s_]", "", value).casefold()


def _read_undefined_variables(directory: Path) -> list[UndefinedRobotVariable]:
    defined_names: set[str] = set()
    resource_file = directory / "common.resource"
    if resource_file.is_file():
        with resource_file.open("r", encoding="utf-8", newline="") as source:
            defined_names.update(
                _normalized_variable_name(variable.name)
                for variable in _read_resource_variables(source.readlines())
            )

    robot_files = sorted(directory.glob("*.robot"), key=lambda path: path.name.casefold())
    for robot_file in robot_files:
        with robot_file.open("r", encoding="utf-8", newline="") as source:
            defined_names.update(
                _normalized_variable_name(variable.name)
                for variable in _read_resource_variables(source.readlines())
            )

    builtin_names = {
        "CURDIR", "TEMPDIR", "EXECDIR", "OUTPUTDIR", "OUTPUTFILE", "LOGFILE",
        "REPORTFILE", "DEBUGFILE", "PREVTESTNAME", "TESTNAME", "TESTDOCUMENTATION",
        "TESTSTATUS", "TESTMESSAGE", "PREVTESTSTATUS", "PREVTESTMESSAGE",
        "SUITENAME", "SUITESOURCE", "SUITEDOCUMENTATION", "SUITESTATUS",
        "SUITEMESSAGE", "KEYWORDSTATUS", "KEYWORDMESSAGE", "LOGLEVEL", "SPACE",
        "EMPTY", "TRUE", "FALSE", "NONE", "/", ":", "\\N", "\\T",
    }
    builtin_names = {_normalized_variable_name(name) for name in builtin_names}
    unresolved: dict[str, UndefinedRobotVariable] = {}
    reference_pattern = re.compile(r"([$@&])\{(?!\{)([^}]+)\}")
    for robot_file in robot_files:
        with robot_file.open("r", encoding="utf-8", newline="") as source:
            in_test_section = False
            for line in source:
                stripped = line.strip()
                if stripped.startswith("***") and stripped.endswith("***"):
                    in_test_section = stripped.casefold() in {
                        "*** test cases ***",
                        "*** tasks ***",
                    }
                    continue
                if not in_test_section or not stripped or stripped.startswith("#"):
                    continue
                if re.match(r"\[(?:Documentation|Tags)\](?:\s|$)", stripped, re.IGNORECASE):
                    continue
                for match in reference_pattern.finditer(line):
                    sigil, raw_name = match.groups()
                    normalized_name = _normalized_variable_name(raw_name)
                    if normalized_name in defined_names or normalized_name in builtin_names:
                        continue

                    name = f"{sigil}{{{raw_name}}}"
                    type_hint: Literal[
                        "scalar", "string", "integer", "float", "boolean", "none",
                        "list", "set", "tuple", "dictionary",
                    ] = (
                        "list" if sigil == "@"
                        else "dictionary" if sigil == "&"
                        else "scalar"
                    )
                    if type_hint == "scalar":
                        suffix = raw_name.replace(" ", "_").upper()
                        if suffix == "TIMEOUT" or suffix.endswith("_TIMEOUT"):
                            type_hint = "integer"
                        elif suffix.endswith("_LIST"):
                            type_hint = "list"
                        elif suffix.endswith("_SET"):
                            type_hint = "set"
                        elif suffix.endswith("_TUPLE"):
                            type_hint = "tuple"
                        elif suffix.endswith("_DICTIONARY"):
                            type_hint = "dictionary"
                    unresolved.setdefault(
                        normalized_name,
                        UndefinedRobotVariable(
                            name=name,
                            type_hint=type_hint,
                            suggested_value={
                                "env": "prod",
                                "user": "admin",
                                "timeout": "30",
                            }.get(normalized_name),
                        ),
                    )
    return sorted(unresolved.values(), key=lambda variable: variable.name.casefold())


def _format_field_value(value: object) -> tuple[str, str]:
    if value is None:
        return "None", "none"
    if isinstance(value, bool):
        return str(value), "boolean"
    if isinstance(value, int):
        return str(value), "integer"
    if isinstance(value, float):
        return str(value), "float"
    return str(value), "string"


def _literal_eval_expression(expression: str) -> object:
    if expression == "set()":
        return set()
    set_match = re.fullmatch(r"set\((.*)\)", expression)
    if set_match:
        try:
            return set(ast.literal_eval(set_match.group(1)))
        except (SyntaxError, ValueError, TypeError) as error:
            raise ValueError("Invalid set expression.") from error
    return ast.literal_eval(expression)


def _parse_cell_value(value: str) -> RobotVariableField:
    expression = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", value)
    if expression:
        try:
            parsed = _literal_eval_expression(expression.group(1))
        except (SyntaxError, ValueError, TypeError):
            pass
        else:
            if parsed is None or isinstance(parsed, (str, int, float, bool)):
                display_value, value_type = _format_field_value(parsed)
                return RobotVariableField(
                    value=display_value,
                    value_type=value_type,
                    expression=True,
                )
    return RobotVariableField(value=value)


def _variable_fields(value: object, *, dictionary: bool = False) -> list[RobotVariableField]:
    if dictionary and isinstance(value, dict):
        fields = []
        for key, item in value.items():
            display_value, value_type = _format_field_value(item)
            fields.append(
                RobotVariableField(key=str(key), value=display_value, value_type=value_type)
            )
        return fields
    if isinstance(value, (list, tuple, set)):
        fields = []
        items = sorted(value, key=repr) if isinstance(value, set) else value
        for item in items:
            display_value, value_type = _format_field_value(item)
            fields.append(RobotVariableField(value=display_value, value_type=value_type))
        return fields
    display_value, value_type = _format_field_value(value)
    return [RobotVariableField(value=display_value, value_type=value_type)]


def _parse_resource_variable(name: str, raw_value: str) -> RobotVariable:
    if name.startswith("&{"):
        fields = []
        for entry in re.split(r"[ \t]{2,}", raw_value.strip()):
            if not entry:
                continue
            key, separator, value = entry.partition("=")
            if separator:
                field = _parse_cell_value(value)
                field.key = key
                fields.append(field)
            else:
                fields.append(RobotVariableField(key=entry, value=""))
        return RobotVariable(name=name, kind="dictionary", fields=fields)

    if name.startswith("@{"):
        items = re.split(r"[ \t]{2,}", raw_value.strip()) if raw_value.strip() else []
        return RobotVariable(
            name=name,
            kind="list",
            fields=[_parse_cell_value(item) for item in items],
        )

    expression_match = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", raw_value)
    if expression_match:
        invalid_literal = object()
        try:
            value = _literal_eval_expression(expression_match.group(1))
        except (SyntaxError, ValueError, TypeError):
            value = invalid_literal
        if isinstance(value, dict):
            return RobotVariable(
                name=name,
                kind="dictionary",
                expression=True,
                fields=_variable_fields(value, dictionary=True),
            )
        if isinstance(value, list):
            return RobotVariable(
                name=name,
                kind="list",
                expression=True,
                fields=_variable_fields(value),
            )
        if isinstance(value, set):
            return RobotVariable(
                name=name,
                kind="set",
                expression=True,
                fields=_variable_fields(value),
            )
        if isinstance(value, tuple):
            return RobotVariable(
                name=name,
                kind="tuple",
                expression=True,
                fields=_variable_fields(value),
            )
        if value is not invalid_literal:
            display_value, value_type = _format_field_value(value)
            return RobotVariable(
                name=name,
                kind="scalar",
                expression=True,
                fields=[RobotVariableField(value=display_value, value_type=value_type)],
            )

    return RobotVariable(
        name=name,
        kind="scalar",
        fields=[RobotVariableField(value=raw_value)],
    )


def _read_resource_variables(lines: list[str]) -> list[RobotVariable]:
    variables: list[RobotVariable] = []
    previously_defined: dict[str, str] = {}
    in_variables_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("***") and stripped.endswith("***"):
            in_variables_section = stripped.casefold() == "*** variables ***"
            continue
        if not in_variables_section or not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^\s*([$@&%]\{[^}]+\})[ \t]{2,}(.*?)(?:\r?\n)?$", line)
        if match:
            name, raw_value = match.groups()
            references = []
            for reference in re.finditer(r"[$@&%]\{([^}]+)\}", raw_value):
                normalized_name = re.sub(r"[\s_]", "", reference.group(1)).casefold()
                defined_name = previously_defined.get(normalized_name)
                if defined_name and defined_name not in references:
                    references.append(defined_name)

            variable = _parse_resource_variable(name, raw_value)
            if len(references) > 1:
                variable.composed_from = references
            variables.append(variable)
            normalized_name = re.sub(r"[\s_]", "", name[2:-1]).casefold()
            previously_defined[normalized_name] = name
    return variables


def _literal_field_value(field: RobotVariableField) -> object:
    if field.value_type == "string":
        return field.value
    try:
        value = ast.literal_eval(field.value)
    except (SyntaxError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {field.value_type} value: {field.value}",
        ) from error
    expected_types = {
        "integer": int,
        "float": float,
        "boolean": bool,
        "none": type(None),
    }
    if type(value) is not expected_types[field.value_type]:
        raise HTTPException(
            status_code=422,
            detail=f"Expected a {field.value_type} value.",
        )
    return value


def _serialize_resource_variable(variable: RobotVariable) -> str:
    if any(
        "\n" in field.value
        or "\r" in field.value
        or "\x00" in field.value
        or (field.key is not None and ("\n" in field.key or "\r" in field.key or "\x00" in field.key))
        for field in variable.fields
    ):
        raise HTTPException(
            status_code=422,
            detail="Variable values must be on a single line.",
        )

    if variable.kind == "scalar":
        if len(variable.fields) != 1:
            raise HTTPException(status_code=422, detail="Scalar variables accept one value.")
        value = _literal_field_value(variable.fields[0]) if variable.expression else variable.fields[0].value
        return "${{" + repr(value) + "}}" if variable.expression else value

    if variable.kind == "dictionary":
        keys = [field.key for field in variable.fields]
        if any(not key or re.search(r"\s|=", key) for key in keys):
            raise HTTPException(
                status_code=422,
                detail="Dictionary keys must be non-empty and cannot contain whitespace or '='.",
            )
        if len(keys) != len(set(keys)):
            raise HTTPException(status_code=422, detail="Dictionary keys must be unique.")
        if variable.name.startswith("&{"):
            return "    ".join(
                f"{field.key}="
                f"{'${{' + repr(_literal_field_value(field)) + '}}' if field.expression else field.value}"
                for field in variable.fields
            )
        if not variable.fields:
            return "${{}}"
        entries = {
            field.key: _literal_field_value(field)
            for field in variable.fields
        }
        return "${{" + repr(entries) + "}}"

    values = [_literal_field_value(field) for field in variable.fields]
    if variable.kind == "list" and variable.name.startswith("@{"):
        return "    ".join(
            "${{" + repr(value) + "}}" if field.expression else str(value)
            for field, value in zip(variable.fields, values)
        )
    if not variable.fields:
        if variable.kind == "list":
            expression = "[]"
        elif variable.kind == "tuple":
            expression = "()"
        else:
            expression = "set()"
        return "${{" + expression + "}}"
    if variable.kind == "list":
        expression = repr(values)
    elif variable.kind == "tuple":
        expression = repr(tuple(values))
    else:
        expression = f"set({values!r})"
    return "${{" + expression + "}}"


def _run_report_name(value: str | None, directory_name: str) -> str:
    if value is None or not value.strip():
        value = f"{directory_name}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    report_name = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_-")
    if not report_name:
        raise HTTPException(
            status_code=422,
            detail="Report name must contain at least one letter or number.",
        )
    return report_name[:100]


def _validate_robot_run(run_request: RobotRunRequest) -> tuple[Path, dict[str, list[str]]]:
    directory = _section_directory(run_request.directory)
    selected_tests: dict[str, list[str]] = {}
    available_tags: set[str] = set()

    for run_file in run_request.files:
        if (
            Path(run_file.name).name != run_file.name
            or not run_file.name.casefold().endswith(".robot")
            or run_file.name in selected_tests
        ):
            raise HTTPException(status_code=422, detail="Invalid or duplicate Robot file.")

        robot_file = directory / run_file.name
        if not robot_file.is_file() or robot_file.resolve().parent != directory.resolve():
            raise HTTPException(
                status_code=422,
                detail=f"Robot file not found: {run_file.name}",
            )

        test_cases = _read_test_cases(robot_file)
        available_tests = {test_case.name for test_case in test_cases}
        if len(run_file.tests) != len(set(run_file.tests)):
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate test case selected in {run_file.name}.",
            )
        unknown_tests = set(run_file.tests) - available_tests
        if unknown_tests:
            raise HTTPException(
                status_code=422,
                detail=f"Test case not found in {run_file.name}: {sorted(unknown_tests)[0]}",
            )
        selected_tests[run_file.name] = run_file.tests
        for test_case in test_cases:
            available_tags.update(test_case.tags)

    if not selected_tests:
        raise HTTPException(status_code=422, detail="Select at least one test case.")

    selected_file_names = set(selected_tests)
    for robot_file in directory.glob("*.robot"):
        if robot_file.name in selected_file_names:
            continue
        for test_case in _read_test_cases(robot_file):
            available_tags.update(test_case.tags)

    available_tags_by_casefold = {tag.casefold(): tag for tag in available_tags}
    for tag in (*run_request.include_tags, *run_request.exclude_tags):
        if tag.casefold() not in available_tags_by_casefold:
            raise HTTPException(status_code=422, detail=f"Unknown tag: {tag}")

    discovered_variables = {
        variable.name for variable in _read_undefined_variables(directory)
    }
    seen_variables: set[str] = set()
    for variable in run_request.variables:
        if variable.name not in discovered_variables:
            raise HTTPException(
                status_code=422,
                detail=f"Variable is not an unresolved variable in this section: {variable.name}",
            )
        if variable.name in seen_variables:
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate variable: {variable.name}",
            )
        if variable.expression or variable.composed_from:
            raise HTTPException(
                status_code=422,
                detail=f"Expressions are not supported for run variable {variable.name}.",
            )
        seen_variables.add(variable.name)

    resource_file = directory / "common.resource"
    if resource_file.is_file():
        with resource_file.open("r", encoding="utf-8", newline="") as source:
            resource_variables = _read_resource_variables(source.readlines())
        resource_variables_by_name = {
            variable.name: variable for variable in resource_variables
        }
        for variable in run_request.predefined_variables:
            existing = resource_variables_by_name.get(variable.name)
            if existing is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown predefined variable: {variable.name}",
                )
            if (
                variable.kind != existing.kind
                or variable.expression != existing.expression
                or len(existing.composed_from) > 1
            ):
                raise HTTPException(
                    status_code=422,
                    detail=f"Predefined variable cannot be changed for {variable.name}.",
                )
            if variable.name in seen_variables:
                raise HTTPException(
                    status_code=422,
                    detail=f"Duplicate variable: {variable.name}",
                )
            seen_variables.add(variable.name)

    return directory, selected_tests


def _run_variable_value(variable: RobotVariable) -> object:
    if variable.kind == "scalar":
        if len(variable.fields) != 1:
            raise HTTPException(
                status_code=422,
                detail=f"Scalar variable {variable.name} requires one value.",
            )
        return _literal_field_value(variable.fields[0])

    if variable.kind == "dictionary":
        result: dict[str, object] = {}
        for field in variable.fields:
            if not field.key or re.search(r"[\s=]", field.key):
                raise HTTPException(
                    status_code=422,
                    detail=f"Dictionary keys for {variable.name} must be non-empty and contain no whitespace or '='.",
                )
            if field.key in result:
                raise HTTPException(
                    status_code=422,
                    detail=f"Dictionary keys for {variable.name} must be unique.",
                )
            result[field.key] = _literal_field_value(field)
        return result

    values = [_literal_field_value(field) for field in variable.fields]
    if variable.kind == "list":
        return values
    if variable.kind == "set":
        return set(values)
    return tuple(values)


def _write_run_variable_file(
    report_name: str,
    directory: Path,
    variables: list[RobotVariable],
    predefined_variables: list[RobotVariable],
) -> Path:
    values: dict[str, object] = {}
    overrides = {variable.name: variable for variable in predefined_variables}
    resource_file = directory / "common.resource"
    if resource_file.is_file():
        with resource_file.open("r", encoding="utf-8", newline="") as resource_source:
            resource_variables = _read_resource_variables(resource_source.readlines())
        for variable in resource_variables:
            override = overrides.get(variable.name)
            match = re.fullmatch(r"[$@&]\{([^}]+)\}", variable.name)
            if match:
                values[match.group(1)] = _run_variable_value(override or variable)

    for variable in variables:
        match = re.fullmatch(r"[$@&]\{([^}]+)\}", variable.name)
        if not match:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid variable name: {variable.name}",
            )
        values[match.group(1)] = _run_variable_value(variable)

    normalized_names = {
        _normalized_variable_name(name): name for name in values
    }
    reference_pattern = re.compile(r"[$@&]\{([^}]+)\}")

    def resolve_variable(name: str, stack: set[str]) -> object:
        if name in stack:
            raise HTTPException(
                status_code=422,
                detail=f"Circular variable reference detected for {name}.",
            )
        return resolve_value(values[name], {*stack, name})

    def resolve_value(value: object, stack: set[str]) -> object:
        if isinstance(value, str):
            def replace_reference(match: re.Match[str]) -> str:
                normalized_reference = _normalized_variable_name(match.group(1))
                referenced_name = normalized_names.get(normalized_reference)
                if referenced_name is None:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Variable reference {match.group(0)} could not be resolved.",
                    )
                return str(resolve_variable(referenced_name, stack))

            return reference_pattern.sub(replace_reference, value)
        if isinstance(value, dict):
            return {
                resolve_value(key, stack): resolve_value(item, stack)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [resolve_value(item, stack) for item in value]
        if isinstance(value, tuple):
            return tuple(resolve_value(item, stack) for item in value)
        if isinstance(value, set):
            return {resolve_value(item, stack) for item in value}
        return value

    values = {
        name: resolve_variable(name, set())
        for name in values
    }
    definitions = [
        f"        {name!r}: {value!r},"
        for name, value in values.items()
    ]
    source = "def get_variables():\n    return {\n"
    source += "\n".join(definitions)
    source += "\n    }\n"
    variable_file = TEMP_DIRECTORY / f"variables_{report_name}.py"
    variable_file.write_text(source, encoding="utf-8")
    return variable_file


def _write_selection_modifier(
    report_name: str,
    directory: Path,
    selected_tests: dict[str, list[str]],
) -> Path:
    selected_sources = {
        str((directory / file_name).resolve()): test_names
        for file_name, test_names in selected_tests.items()
    }
    source = (
        "from pathlib import Path\n"
        f"SELECTED_TESTS = {selected_sources!r}\n\n"
        "def visit_suite(suite):\n"
        "    if suite.source and str(Path(suite.source).resolve()).casefold().endswith('.robot'):\n"
        "        selected = SELECTED_TESTS.get(str(Path(suite.source).resolve()))\n"
        "        suite.tests[:] = [test for test in suite.tests if selected and test.name in selected]\n"
        "    for child in suite.suites:\n"
        "        visit_suite(child)\n"
    )
    modifier_file = TEMP_DIRECTORY / f"robot_selection_{report_name}.py"
    modifier_file.write_text(source, encoding="utf-8")
    return modifier_file


def _write_progress_listener(report_name: str) -> Path:
    source = (
        "ROBOT_LISTENER_API_VERSION = 3\n\n"
        "def end_test(data, result):\n"
        "    print('__ROBOT_RUN_PROGRESS__', flush=True)\n"
    )
    listener_file = TEMP_DIRECTORY / f"robot_progress_{report_name}.py"
    listener_file.write_text(source, encoding="utf-8")
    return listener_file


def _build_robot_command(
    report_name: str,
    directory: Path,
    selected_tests: dict[str, list[str]],
    variables: list[RobotVariable],
    predefined_variables: list[RobotVariable],
    include_tags: list[str],
    exclude_tags: list[str],
) -> tuple[list[str], RobotRunPaths]:
    variable_file = _write_run_variable_file(
        report_name,
        directory,
        variables,
        predefined_variables,
    )
    modifier_file = _write_selection_modifier(report_name, directory, selected_tests)
    progress_listener = _write_progress_listener(report_name)
    report_directory = REPORTS_DIRECTORY / report_name
    report_directory.mkdir(parents=True, exist_ok=True)
    output_file = report_directory / f"{report_name}_output.xml"
    log_file = report_directory / f"{report_name}_log.html"
    report_file = report_directory / f"{report_name}_report.html"

    command = [
        sys.executable,
        "-u",
        "-m",
        "robot",
        "--output",
        str(output_file),
        "--log",
        str(log_file),
        "--report",
        str(report_file),
        "--variablefile",
        str(variable_file),
        "--prerunmodifier",
        str(modifier_file),
        "--listener",
        str(progress_listener),
    ]
    for tag in include_tags:
        command.extend(["--include", tag])
    for tag in exclude_tags:
        command.extend(["--exclude", tag])
    command.append(str(directory))
    return command, RobotRunPaths(
        variable_file=variable_file,
        modifier_file=modifier_file,
        output_file=output_file,
        log_file=log_file,
        report_file=report_file,
        progress_listener=progress_listener,
    )


async def _append_run_output(run_id: str, text: str) -> None:
    run = RUNS[run_id]
    async with RUN_OUTPUT_LOCKS[run_id]:
        output = str(run["console_output"]) + text
        truncated = bool(run["console_output_truncated"])
        if len(output) > MAX_RUN_OUTPUT_CHARS:
            output = output[-MAX_RUN_OUTPUT_CHARS:]
            truncated = True
        run["console_output"] = output
        run["console_output_truncated"] = truncated
        with _database_connection() as connection:
            connection.execute(
                "UPDATE runs SET console_output = console_output || ? WHERE id = ?",
                (text, run_id),
            )
        message = {"type": "output", "text": text}
        disconnected: set[WebSocket] = set()
        for websocket in RUN_OUTPUT_SOCKETS.get(run_id, set()):
            try:
                await websocket.send_json(message)
            except (OSError, RuntimeError, WebSocketDisconnect):
                disconnected.add(websocket)
        RUN_OUTPUT_SOCKETS.get(run_id, set()).difference_update(disconnected)


async def _update_run_progress(run_id: str) -> None:
    run = RUNS[run_id]
    run["progress_current"] = min(
        int(run["progress_total"]),
        int(run["progress_current"]) + 1,
    )
    _persist_run_state(run)
    for websocket in tuple(RUN_OUTPUT_SOCKETS.get(run_id, set())):
        try:
            await websocket.send_json(
                {
                    "type": "progress",
                    "current": run["progress_current"],
                    "total": run["progress_total"],
                }
            )
        except (OSError, RuntimeError, WebSocketDisconnect):
            RUN_OUTPUT_SOCKETS.get(run_id, set()).discard(websocket)


async def _execute_robot_run(
    run_id: str,
    command: list[str],
) -> None:
    run = RUNS[run_id]
    try:
        run["started_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        logger.info("Starting Robot run %s (%s)", run_id, run["report_name"])
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=APP_DIRECTORY,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        run.update(status="running", process_id=process.pid)
        RUN_PROCESSES[run_id] = process
        _persist_run_state(run)
        if process.stdout is None:
            raise RuntimeError("Robot Framework stdout pipe was not created.")
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while line := await process.stdout.readline():
            text = decoder.decode(line)
            if "__ROBOT_RUN_PROGRESS__" in text:
                output_text = text.replace("__ROBOT_RUN_PROGRESS__", "")
                if output_text:
                    await _append_run_output(run_id, output_text)
                await _update_run_progress(run_id)
            else:
                await _append_run_output(run_id, text)
        trailing_text = decoder.decode(b"", final=True)
        if trailing_text:
            await _append_run_output(run_id, trailing_text)
        return_code = await process.wait()
        RUN_PROCESSES.pop(run_id, None)
        run["progress_current"] = run["progress_total"]
        run.update(
            status="completed" if return_code == 0 else "failed",
            exit_code=return_code,
            finished_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            message=(
                "Robot Framework finished successfully."
                if return_code == 0
                else f"Robot Framework finished with exit code {return_code}."
            ),
        )
        logger.info(
            "Robot run %s finished with status %s and exit code %s",
            run_id,
            run["status"],
            return_code,
        )
    except OSError as error:
        logger.exception("Could not start Robot run %s", run_id)
        run.update(
            status="failed",
            finished_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            message=f"Could not start Robot Framework: {error}",
        )
    except RuntimeError as error:
        logger.exception("Robot run %s output stream failed", run_id)
        run.update(
            status="failed",
            finished_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            message=f"Robot Framework output stream failed: {error}",
        )
    finally:
        RUN_PROCESSES.pop(run_id, None)
        run["report_url"] = (
            f"/reports/{run['report_name']}/{run['report_name']}_report.html"
            if Path(str(run["report_file"])).is_file()
            else None
        )
        report_name = str(run["report_name"])
        report_directory = REPORTS_DIRECTORY / report_name
        run["log_url"] = (
            f"/reports/{report_name}/{report_name}_log.html"
            if (report_directory / f"{report_name}_log.html").is_file()
            else None
        )
        run["output_url"] = (
            f"/reports/{report_name}/{report_name}_output.xml"
            if (report_directory / f"{report_name}_output.xml").is_file()
            else None
        )
        _persist_run_state(run)
        for websocket in tuple(RUN_OUTPUT_SOCKETS.get(run_id, set())):
            try:
                await websocket.send_json(
                    {
                        "type": "status",
                        "status": run["status"],
                        "progress_current": run["progress_current"],
                        "progress_total": run["progress_total"],
                    }
                )
            except (OSError, RuntimeError, WebSocketDisconnect):
                RUN_OUTPUT_SOCKETS.get(run_id, set()).discard(websocket)
        RUN_TASKS.pop(run_id, None)


def _prepare_run(run_request: RobotRunRequest) -> PreparedRobotRun:
    directory, selected_tests = _validate_robot_run(run_request)
    report_name = _run_report_name(run_request.report_name, directory.name)
    if any(
        run.get("report_name") == report_name
        and run.get("status") in {"queued", "running"}
        for run in RUNS.values()
    ):
        raise HTTPException(
            status_code=409,
            detail=f"A run named {report_name} is already in progress.",
        )
    report_directory = REPORTS_DIRECTORY / report_name
    if any(
        (report_directory / f"{report_name}_{suffix}").exists()
        for suffix in ("report.html", "log.html", "output.xml")
    ):
        raise HTTPException(
            status_code=409,
            detail=f"A report named {report_name} already exists. Choose a different report name.",
        )
    command, paths = _build_robot_command(
        report_name,
        directory,
        selected_tests,
        run_request.variables,
        run_request.predefined_variables,
        run_request.include_tags,
        run_request.exclude_tags,
    )
    return PreparedRobotRun(report_name=report_name, command=command, paths=paths)


@app.post("/api/runs/preview")
async def preview_robot_run(run_request: RobotRunRequest) -> dict[str, str]:
    prepared = _prepare_run(run_request)
    return {
        "report_name": prepared.report_name,
        "command": shlex.join(prepared.command),
    }


@app.post("/api/runs")
async def start_robot_run(run_request: RobotRunRequest) -> dict[str, str]:
    prepared = _prepare_run(run_request)
    report_name = prepared.report_name

    run_id = uuid.uuid4().hex
    command = prepared.command
    paths = prepared.paths
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    progress_total = sum(len(run_file.tests) for run_file in run_request.files)
    RUNS[run_id] = {
        "id": run_id,
        "status": "queued",
        "report_name": report_name,
        "directory": run_request.directory,
        "command": shlex.join(command),
        "process_id": None,
        "created_at": created_at,
        "started_at": None,
        "finished_at": None,
        "exit_code": None,
        "message": "Run queued.",
        "console_output": "",
        "console_output_truncated": False,
        "progress_current": 0,
        "progress_total": progress_total,
        "report_file": str(paths.report_file),
        "report_url": None,
        "log_url": None,
        "output_url": None,
    }
    with _database_connection() as connection:
        connection.execute(
            """
            INSERT INTO runs (
                id, report_name, directory, status, command, process_id,
                created_at, started_at, finished_at, exit_code, message,
                console_output, progress_current, progress_total, report_url,
                log_url, output_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, report_name, run_request.directory, "queued",
                str(RUNS[run_id]["command"]), None, created_at, None, None, None,
                "Run queued.", "", 0, progress_total, None, None, None,
            ),
        )
    RUN_OUTPUT_SOCKETS[run_id] = set()
    RUN_OUTPUT_LOCKS[run_id] = asyncio.Lock()
    RUN_TASKS[run_id] = asyncio.create_task(
        _execute_robot_run(run_id, command)
    )
    return {
        "run_id": run_id,
        "report_name": report_name,
        "command": str(RUNS[run_id]["command"]),
        "status": "queued",
    }


@app.get("/api/runs")
async def list_robot_runs() -> list[dict[str, object]]:
    return [
        {
            key: value
            for key, value in run.items()
            if key not in {"console_output", "console_output_truncated", "report_file"}
        }
        for run in sorted(
            RUNS.values(),
            key=lambda item: str(item.get("created_at", "")),
            reverse=True,
        )
    ]


@app.get("/api/runs/{run_id}")
async def get_robot_run(run_id: str) -> dict[str, object]:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Robot run not found.")
    response = {
        key: value
        for key, value in run.items()
        if key not in {
            "report_file",
            "console_output",
            "console_output_truncated",
        }
    }
    output = str(run["console_output"])
    response["console_output"] = output[-MAX_RUN_OUTPUT_CHARS:]
    response["console_output_truncated"] = bool(run["console_output_truncated"])
    return response


async def _stop_robot_run(run_id: str) -> dict[str, object]:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Robot run not found.")
    if run["status"] not in {"queued", "running"}:
        return run

    process = RUN_PROCESSES.get(run_id)
    task = RUN_TASKS.get(run_id)
    if process is None and task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    elif process is not None and process.returncode is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(asyncio.shield(process.wait()), timeout=5)
        except asyncio.TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    if task is not None and not task.done():
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=8)
        except asyncio.TimeoutError:
            task.cancel()
        except asyncio.CancelledError:
            pass

    run.update(
        status="killed",
        exit_code=run.get("exit_code"),
        finished_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        message="Robot Framework process was stopped.",
    )
    logger.info("Robot run %s was stopped", run_id)
    RUN_TASKS.pop(run_id, None)
    _persist_run_state(run)
    for websocket in tuple(RUN_OUTPUT_SOCKETS.get(run_id, set())):
        try:
            await websocket.send_json({"type": "status", "status": "killed"})
        except (OSError, RuntimeError, WebSocketDisconnect):
            RUN_OUTPUT_SOCKETS.get(run_id, set()).discard(websocket)
    return run


@app.post("/api/runs/{run_id}/kill")
async def kill_robot_run(run_id: str) -> dict[str, object]:
    run = await _stop_robot_run(run_id)
    return {"id": run_id, "status": run["status"], "message": run["message"]}


@app.delete("/api/runs/{run_id}", status_code=204)
async def delete_robot_run(run_id: str) -> None:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Robot run not found.")
    if run["status"] in {"queued", "running"}:
        raise HTTPException(
            status_code=409,
            detail="Stop the process before deleting its information.",
        )
    for websocket in tuple(RUN_OUTPUT_SOCKETS.get(run_id, set())):
        await websocket.close(code=1000, reason="Run history deleted.")
    with _database_connection() as connection:
        connection.execute("DELETE FROM runs WHERE id = ?", (run_id,))
    RUNS.pop(run_id, None)
    RUN_OUTPUT_SOCKETS.pop(run_id, None)
    RUN_OUTPUT_LOCKS.pop(run_id, None)


@app.post("/api/runs/stop-all-and-clear")
async def stop_all_runs_and_clear_history() -> dict[str, int]:
    run_ids = list(RUNS)
    for run_id in run_ids:
        if RUNS[run_id]["status"] in {"queued", "running"}:
            await _stop_robot_run(run_id)
    with _database_connection() as connection:
        connection.execute("DELETE FROM runs")
    for run_id in run_ids:
        RUNS.pop(run_id, None)
        for websocket in tuple(RUN_OUTPUT_SOCKETS.get(run_id, set())):
            await websocket.close(code=1000, reason="Run history cleared.")
        RUN_OUTPUT_SOCKETS.pop(run_id, None)
        RUN_OUTPUT_LOCKS.pop(run_id, None)
    return {"removed": len(run_ids)}


def _safe_report_directory(report_name: str) -> Path:
    if (
        not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", report_name)
        or report_name in {".", ".."}
    ):
        raise HTTPException(status_code=422, detail="Invalid report name.")
    report_directory = REPORTS_DIRECTORY / report_name
    if report_directory.resolve().parent != REPORTS_DIRECTORY.resolve():
        raise HTTPException(status_code=422, detail="Invalid report name.")
    return report_directory


def _report_summary(report_directory: Path) -> dict[str, object] | None:
    report_name = report_directory.name
    report_file = report_directory / f"{report_name}_report.html"
    log_file = report_directory / f"{report_name}_log.html"
    output_file = report_directory / f"{report_name}_output.xml"
    if not any(path.is_file() for path in (report_file, log_file, output_file)):
        return None
    created_at = max(
        path.stat().st_mtime
        for path in (report_file, log_file, output_file)
        if path.is_file()
    )
    return {
        "name": report_name,
        "report_url": f"/reports/{report_name}/{report_file.name}" if report_file.is_file() else None,
        "log_url": f"/reports/{report_name}/{log_file.name}" if log_file.is_file() else None,
        "output_url": f"/reports/{report_name}/{output_file.name}" if output_file.is_file() else None,
        "created_at": datetime.fromtimestamp(created_at).astimezone().isoformat(timespec="seconds"),
    }


@app.get("/api/reports")
async def list_robot_reports() -> list[dict[str, object]]:
    return sorted(
        (
            summary
            for directory in REPORTS_DIRECTORY.iterdir()
            if directory.is_dir()
            and (summary := _report_summary(directory)) is not None
        ),
        key=lambda report: str(report["created_at"]),
        reverse=True,
    )


@app.delete("/api/reports/{report_name}", status_code=204)
async def delete_robot_report(report_name: str) -> None:
    report_directory = _safe_report_directory(report_name)
    if not report_directory.is_dir() or _report_summary(report_directory) is None:
        raise HTTPException(status_code=404, detail="Robot report not found.")
    shutil.rmtree(report_directory)
    with _database_connection() as connection:
        connection.execute(
            """
            UPDATE runs
            SET report_url = NULL, log_url = NULL, output_url = NULL
            WHERE report_name = ?
            """,
            (report_name,),
        )
    for run_id, run in tuple(RUNS.items()):
        if run.get("report_name") == report_name:
            run.update(report_url=None, log_url=None, output_url=None)


@app.post("/api/reports/archive")
async def download_robot_reports(selection: RobotReportSelection) -> FileResponse:
    report_names = list(dict.fromkeys(selection.report_names))
    if len(report_names) != len(selection.report_names):
        raise HTTPException(status_code=422, detail="Select each report only once.")
    with tempfile.NamedTemporaryFile(
        prefix="robot-reports-",
        suffix=".zip",
        dir=TEMP_DIRECTORY,
        delete=False,
    ) as temporary_archive:
        archive_path = Path(temporary_archive.name)
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
            for report_name in report_names:
                report_directory = _safe_report_directory(report_name)
                if not report_directory.is_dir() or _report_summary(report_directory) is None:
                    raise HTTPException(status_code=404, detail=f"Robot report not found: {report_name}")
                for report_file in report_directory.rglob("*"):
                    if report_file.is_file() and not report_file.is_symlink():
                        zipped.write(report_file, report_file.relative_to(REPORTS_DIRECTORY))
    except BaseException:
        archive_path.unlink(missing_ok=True)
        raise
    filename = "robot-reports.zip" if len(report_names) > 1 else f"{report_names[0]}.zip"
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )


@app.post("/api/reports/merge")
async def merge_robot_reports(request: RobotReportMergeRequest) -> dict[str, object]:
    report_names = list(dict.fromkeys(request.report_names))
    if len(report_names) != len(request.report_names):
        raise HTTPException(status_code=422, detail="Select each report only once.")
    report_name = _run_report_name(request.report_name, "merged")
    if report_name in report_names:
        raise HTTPException(
            status_code=422,
            detail="Choose a new name for the merged report.",
        )
    source_files: list[Path] = []
    for source_name in report_names:
        source_directory = _safe_report_directory(source_name)
        output_file = source_directory / f"{source_name}_output.xml"
        if not output_file.is_file():
            raise HTTPException(
                status_code=422,
                detail=f"Report {source_name} does not contain output.xml and cannot be merged.",
            )
        source_files.append(output_file)

    destination = _safe_report_directory(report_name)
    if destination.exists():
        raise HTTPException(
            status_code=409,
            detail=f"A report named {report_name} already exists.",
        )
    destination.mkdir()
    output_file = destination / f"{report_name}_output.xml"
    log_file = destination / f"{report_name}_log.html"
    report_file = destination / f"{report_name}_report.html"
    command = [
        sys.executable,
        "-u",
        "-m",
        "robot.rebot",
        "--merge",
        "--output",
        str(output_file),
        "--log",
        str(log_file),
        "--report",
        str(report_file),
        *(str(path) for path in source_files),
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=APP_DIRECTORY,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        raise HTTPException(
            status_code=422,
            detail=stdout.decode("utf-8", errors="replace")[-4000:]
            or f"Robot Framework Rebot exited with code {process.returncode}.",
        )
    summary = _report_summary(destination)
    if summary is None:
        raise HTTPException(
            status_code=500,
            detail="Robot Framework Rebot completed without creating report files.",
        )
    logger.info("Merged Robot reports %s into %s", report_names, report_name)
    return summary


@app.get("/api/directories/{directory_name}/files", response_model=list[RobotFile])
async def list_robot_files(directory_name: str) -> list[RobotFile]:
    directory = _section_directory(directory_name)

    try:
        robot_files = []
        for robot_file in sorted(directory.glob("*.robot"), key=lambda path: path.name.casefold()):
            display_name = re.sub(r"[-_]+", " ", robot_file.stem).title()
            robot_files.append(
                RobotFile(
                    name=robot_file.name,
                    display_name=display_name,
                    test_cases=_read_test_cases(robot_file),
                )
            )
        return robot_files
    except (OSError, UnicodeError) as error:
        raise HTTPException(
            status_code=500,
            detail="Unable to read Robot Framework files.",
        ) from error


@app.get(
    "/api/directories/{directory_name}/variables",
    response_model=list[RobotVariable],
)
async def get_robot_variables(directory_name: str) -> list[RobotVariable]:
    resource_file = _section_directory(directory_name) / "common.resource"
    if not resource_file.is_file():
        raise HTTPException(status_code=404, detail="common.resource not found.")
    try:
        with resource_file.open("r", encoding="utf-8", newline="") as source:
            return _read_resource_variables(source.readlines())
    except (OSError, UnicodeError) as error:
        raise HTTPException(
            status_code=500,
            detail="Unable to read common.resource.",
        ) from error


@app.get(
    "/api/directories/{directory_name}/undefined-variables",
    response_model=list[UndefinedRobotVariable],
)
async def get_undefined_robot_variables(
    directory_name: str,
) -> list[UndefinedRobotVariable]:
    directory = _section_directory(directory_name)
    try:
        return _read_undefined_variables(directory)
    except (OSError, UnicodeError) as error:
        raise HTTPException(
            status_code=500,
            detail="Unable to inspect Robot Framework variables.",
        ) from error


@app.put(
    "/api/directories/{directory_name}/variables",
    response_model=list[RobotVariable],
)
async def update_robot_variables(
    directory_name: str,
    update: RobotVariablesUpdate,
) -> list[RobotVariable]:
    resource_file = _section_directory(directory_name) / "common.resource"
    if not resource_file.is_file():
        raise HTTPException(status_code=404, detail="common.resource not found.")

    names = [variable.name for variable in update.variables]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=422, detail="Variable names must be unique.")

    try:
        with resource_file.open("r", encoding="utf-8", newline="") as source:
            lines = source.readlines()
        existing_variables = _read_resource_variables(lines)
        existing_by_name = {variable.name: variable for variable in existing_variables}
        existing_names = set(existing_by_name)
        unknown_names = set(names) - existing_names
        if unknown_names:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown variable name: {sorted(unknown_names)[0]}",
            )

        values = {}
        for variable in update.variables:
            existing_variable = existing_by_name[variable.name]
            if (
                variable.kind != existing_variable.kind
                or variable.expression != existing_variable.expression
            ):
                raise HTTPException(
                    status_code=422,
                    detail=f"Variable type cannot be changed for {variable.name}.",
                )
            values[variable.name] = _serialize_resource_variable(variable)

        in_variables_section = False
        updated_names: set[str] = set()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("***") and stripped.endswith("***"):
                in_variables_section = stripped.casefold() == "*** variables ***"
                continue
            if not in_variables_section:
                continue
            match = re.match(
                r"^(\s*)([$@&%]\{[^}]+\})([ \t]{2,})(.*?)(\r?\n)?$",
                line,
            )
            if match and match.group(2) in values:
                lines[index] = (
                    f"{match.group(1)}{match.group(2)}{match.group(3)}"
                    f"{values[match.group(2)]}{match.group(5) or ''}"
                )
                updated_names.add(match.group(2))

        if updated_names != set(values):
            raise HTTPException(
                status_code=409,
                detail="common.resource changed while saving. Reload and try again.",
            )

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=resource_file.parent,
                delete=False,
            ) as temporary_file:
                temporary_file.write("".join(lines))
                temporary_path = Path(temporary_file.name)
            temporary_path.chmod(resource_file.stat().st_mode)
            temporary_path.replace(resource_file)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
        return _read_resource_variables(lines)
    except HTTPException:
        raise
    except (OSError, UnicodeError) as error:
        raise HTTPException(
            status_code=500,
            detail="Unable to update common.resource.",
        ) from error


@app.websocket("/ws")
async def websocket_hello(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_text("Hello World")
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/runs/{run_id}")
async def websocket_run_output(websocket: WebSocket, run_id: str) -> None:
    run = RUNS.get(run_id)
    if run is None:
        await websocket.accept()
        await websocket.close(code=4404, reason="Robot run not found.")
        return

    await websocket.accept()
    lock = RUN_OUTPUT_LOCKS[run_id]
    subscribers = RUN_OUTPUT_SOCKETS[run_id]
    try:
        async with lock:
            subscribers.add(websocket)
            console_output = str(run["console_output"])
            await websocket.send_json(
                {
                    "type": "snapshot",
                    "text": console_output[-MAX_RUN_OUTPUT_CHARS:],
                    "truncated": (
                        bool(run["console_output_truncated"])
                        or len(console_output) > MAX_RUN_OUTPUT_CHARS
                    ),
                    "status": run["status"],
                    "progress_current": run["progress_current"],
                    "progress_total": run["progress_total"],
                }
            )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        async with lock:
            subscribers.discard(websocket)


@app.on_event("shutdown")
async def stop_robot_runs_on_server_shutdown() -> None:
    for run_id, run in tuple(RUNS.items()):
        if run["status"] in {"queued", "running"}:
            await _stop_robot_run(run_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=APP_CONFIG.ip_address, port=APP_CONFIG.port)