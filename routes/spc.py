"""SPC API routes."""

from fastapi import APIRouter

from services.spc_service import get_spc_active, get_spc_outlook, get_spc_reports

router = APIRouter()


@router.get("/api/data/spc")
def get_data_spc(day: int = 1, hazard: str = "cat"):
    return get_spc_outlook(day=day, hazard=hazard)


@router.get("/api/data/spc/reports")
def get_data_spc_reports(
    day: str = "today",
    report_mode: str = "filtered",
    report_type: str = "all",
):
    return get_spc_reports(day=day, report_mode=report_mode, report_type=report_type)


@router.get("/api/data/spc/active")
def get_data_spc_active(
    product: str = "watches",
    watch_mode: str = "polygon",
    watch_types: str = "all",
):
    return get_spc_active(
        product=product,
        watch_mode=watch_mode,
        watch_types=watch_types,
    )
