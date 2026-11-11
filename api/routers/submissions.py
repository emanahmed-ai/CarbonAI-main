"""Report submission workflow endpoints (factory -> head office) and the consolidated view."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Auth, current_user, get_con, require, resolve_scope
from services import submissions as S

router = APIRouter(prefix="/api/submissions", tags=["submissions"])


class SubmitIn(BaseModel):
    facility_id: int | None = None
    period_year: int
    period_month: int | None = None
    title: str = ""
    allow_supersede: bool = False


class ReviewIn(BaseModel):
    decision: str
    note: str = ""


@router.post("", status_code=201)
def create_submission(body: SubmitIn, con=Depends(get_con),
                      user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    if body.facility_id is not None and user.is_factory_scoped and body.facility_id != user.facility_id:
        raise HTTPException(403, "you can only submit reports for your own facility")
    facility_id = body.facility_id if not user.is_factory_scoped else user.facility_id
    if facility_id is None:
        raise HTTPException(400, "facility_id is required")
    if user.is_factory_scoped and facility_id != user.facility_id:
        raise HTTPException(403, "you can only submit reports for your own facility")
    try:
        return S.create_submission(con, facility_id=facility_id, period_year=body.period_year,
                                   period_month=body.period_month, submitted_by=user.username,
                                   title=body.title, company_id=user.company_id,
                                   allow_supersede=body.allow_supersede)
    except S.SubmissionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("")
def list_submissions(facility_id: int | None = None, company_id: int | None = None,
                     status: str | None = None, year: int | None = None, con=Depends(get_con),
                     user: Auth = Depends(current_user)):
    cid, fid = resolve_scope(user, company_id, facility_id)
    if user.is_factory_scoped:
        cid, fid = user.company_id, user.facility_id
    return S.list_submissions(con, company_id=cid, facility_id=fid, status=status, year=year)


@router.get("/consolidated")
def consolidated(year: int | None = None, company_id: int | None = None, con=Depends(get_con),
                 user: Auth = Depends(require("admin", "head_office"))):
    cid, _ = resolve_scope(user, company_id, None)
    return S.consolidated(con, company_id=cid, year=year)


@router.get("/{submission_id}")
def submission_detail(submission_id: int, con=Depends(get_con), user: Auth = Depends(current_user)):
    d = S.submission_detail(con, submission_id)
    if d is None:
        raise HTTPException(404, "submission not found")
    if user.is_factory_scoped and d["facility_id"] != user.facility_id:
        raise HTTPException(403, "submission belongs to another facility")
    if user.role == "head_office" and user.company_id is not None and d["company_id"] != user.company_id:
        raise HTTPException(403, "submission belongs to another company")
    return d


@router.post("/{submission_id}/review")
def review(submission_id: int, body: ReviewIn, con=Depends(get_con),
           user: Auth = Depends(require("admin", "head_office"))):
    d = S.submission_detail(con, submission_id)
    if d is None:
        raise HTTPException(404, "submission not found")
    if user.role == "head_office" and user.company_id is not None and d["company_id"] != user.company_id:
        raise HTTPException(403, "submission belongs to another company")
    try:
        return S.review_submission(con, submission_id, decision=body.decision,
                                   reviewer=user.username, note=body.note)
    except S.SubmissionError as e:
        raise HTTPException(409, str(e))


@router.get("/{submission_id}/audit")
def submission_audit(submission_id: int, con=Depends(get_con), user: Auth = Depends(current_user)):
    d = S.submission_detail(con, submission_id)
    if d is None:
        raise HTTPException(404, "submission not found")
    if user.is_factory_scoped and d["facility_id"] != user.facility_id:
        raise HTTPException(403, "submission belongs to another facility")
    from api.util import rows_list
    return rows_list(con.execute("SELECT * FROM submission_audit_log WHERE submission_id=? ORDER BY id",
                                 (submission_id,)).fetchall())
