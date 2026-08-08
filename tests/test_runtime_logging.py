import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUEST_PATH_MODULES = (
    "routes/satellite_v2.py",
    "satellite_v2/service.py",
    "satellite_v2/tiler.py",
    "services/alerts_service.py",
    "services/boundary_service.py",
    "services/overlay_service.py",
    "services/radar_service.py",
    "services/tropical_service.py",
    "surface/surface_utils.py",
)
PRODUCTION_ROOTS = (
    "app_core",
    "lib",
    "mrms",
    "radar",
    "routes",
    "rtma",
    "satellite_v2",
    "services",
    "surface",
    "workers",
)
STDOUT_CONTRACT_MODULES = {
    "radar/bench.py",
    "satellite_v2/bench.py",
    "workers/optional_warmer.py",
}


def _production_modules():
    for root_name in PRODUCTION_ROOTS:
        for path in (ROOT / root_name).rglob("*.py"):
            yield path, path.relative_to(ROOT).as_posix()


def test_request_path_modules_use_logging_instead_of_print():
    for relative_path in REQUEST_PATH_MODULES:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative_path)
        print_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ]
        assert not print_calls, relative_path


def test_request_path_exception_logs_do_not_format_exception_payloads():
    for relative_path in REQUEST_PATH_MODULES:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative_path)
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"_LOGGER", "logger"}
            ):
                continue

            for argument in node.args[1:]:
                assert not (
                    isinstance(argument, ast.Name) and argument.id == "exc"
                ), relative_path
                assert not (
                    isinstance(argument, ast.Call)
                    and isinstance(argument.func, ast.Name)
                    and argument.func.id == "str"
                    and any(
                        isinstance(item, ast.Name) and item.id == "exc"
                        for item in argument.args
                    )
                ), relative_path

            assert not any(
                keyword.arg == "exc_info"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            ), relative_path


def test_production_modules_reserve_print_for_explicit_stdout_contracts():
    for path, relative_path in _production_modules():
        if relative_path in STDOUT_CONTRACT_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                continue
            allowed_alerts_measurement = (
                relative_path == "workers/alerts_worker.py"
                and node.args
                and isinstance(node.args[0], ast.Call)
                and isinstance(node.args[0].func, ast.Attribute)
                and node.args[0].func.attr == "dumps"
            )
            assert allowed_alerts_measurement, relative_path


def test_production_logging_does_not_emit_tracebacks():
    for path, relative_path in _production_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            assert not (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "traceback"
                and node.func.attr in {"print_exc", "format_exc"}
            ), relative_path
            assert not any(
                keyword.arg == "exc_info"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            ), relative_path
