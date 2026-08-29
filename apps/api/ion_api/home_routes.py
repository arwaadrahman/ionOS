from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException

from ion_api.home import HomeService
from ion_api.home_contracts import HomeOutput
from ion_api.today import TodayValidationError
from ion_api.today_contracts import TodayContext


def home_router(service: HomeService) -> APIRouter:
    router = APIRouter(prefix="/v1/home", tags=["home"])

    @router.get("", response_model=HomeOutput)
    def get_home(planning_date: date, timezone: str):
        try:
            return service.get_home(
                TodayContext(planning_date=planning_date, timezone=timezone)
            )
        except TodayValidationError as error:
            raise HTTPException(
                422, detail={"code": "validation", "blockers": []}
            ) from error

    return router
