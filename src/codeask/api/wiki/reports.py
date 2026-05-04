"""Wiki report projection routes."""

from dataclasses import asdict

from fastapi import APIRouter

from codeask.api.wiki.deps import SessionDep, load_feature
from codeask.api.wiki.schemas import (
    WikiReportDetailRead,
    WikiReportProjectionListRead,
    WikiReportProjectionRead,
)
from codeask.wiki.report_projection import WikiReportProjectionService

router = APIRouter()


@router.get("/reports/projections", response_model=WikiReportProjectionListRead)
async def list_report_projections(
    feature_id: int,
    session: SessionDep,
) -> WikiReportProjectionListRead:
    feature = await load_feature(feature_id, session)
    projections = await WikiReportProjectionService().list_projections(
        session,
        feature_id=feature.id,
    )
    return WikiReportProjectionListRead(
        items=[WikiReportProjectionRead(**asdict(projection)) for projection in projections]
    )


@router.get("/reports/by-node/{node_id}", response_model=WikiReportDetailRead)
async def get_report_by_node(node_id: int, session: SessionDep) -> WikiReportDetailRead:
    detail = await WikiReportProjectionService().get_report_by_node(session, node_id=node_id)
    return WikiReportDetailRead(**asdict(detail))
