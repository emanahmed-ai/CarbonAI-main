"""Invoices & documents API: manual entry + upload, extraction review, calculation, search,
archive, voiding (no deletion), duplicate prevention and audit history."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.deps import Auth, current_user, get_con, require, resolve_scope
from services import invoices as INV

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


class CalculateIn(BaseModel):
    """Manual factor entry is intentionally absent: the Core selects the factor by invoice year."""
    factor_id: str | None = None
    factor_version: int | None = None
    ownership_control: str = "unknown"
    energy_purchased: str = "unknown"
    value_chain_relation: str = "unknown"


class VoidIn(BaseModel):
    reason: str


def _facility_for_write(con, user: Auth, facility_id: int | None) -> tuple[int, int]:
    if user.is_factory_scoped:
        if facility_id is not None and facility_id != user.facility_id:
            raise HTTPException(403, "you can only register invoices for your own facility")
        facility_id = user.facility_id
    if facility_id is None:
        raise HTTPException(400, "facility_id is required")
    fac = con.execute("SELECT company_id FROM facilities WHERE facility_id=?", (facility_id,)).fetchone()
    if fac is None:
        raise HTTPException(404, "facility not found")
    if user.role == "head_office" and fac["company_id"] != user.company_id:
        raise HTTPException(403, "facility belongs to another company")
    return facility_id, fac["company_id"]


@router.get("")
def list_invoices(company_id: int | None = None, facility_id: int | None = None,
                  search: str | None = None, year: int | None = None, month: int | None = None,
                  status: str | None = None, category: str | None = None,
                  con=Depends(get_con), user: Auth = Depends(current_user)):
    cid, fid = resolve_scope(user, company_id, facility_id)
    return INV.list_invoices(con, company_id=cid, facility_id=fid, search=search, year=year,
                             month=month, status=status, category=category)


@router.post("", status_code=201)
def create_invoice(
    invoice_name: str = Form(...), facility_id: int | None = Form(None),
    invoice_number: str | None = Form(None), supplier: str | None = Form(None),
    invoice_date: str | None = Form(None), period_year: int | None = Form(None),
    period_month: int | None = Form(None), category_key: str | None = Form(None),
    quantity: str | None = Form(None), unit: str | None = Form(None),
    amount: str | None = Form(None), currency: str = Form("EGP"), notes: str = Form(""),
    confirm_duplicate: bool = Form(False),
    file: UploadFile | None = File(None),
    con=Depends(get_con), user: Auth = Depends(require("admin", "head_office", "factory_manager")),
):
    fid, cid = _facility_for_write(con, user, facility_id)
    upload = None
    if file is not None:
        data = file.file.read()
        upload = (file.filename or "invoice.pdf", file.content_type or "", data)
    try:
        return INV.create_invoice(
            con, facility_id=fid, company_id=cid, invoice_name=invoice_name,
            invoice_number=invoice_number, supplier=supplier, invoice_date=invoice_date,
            period_year=period_year, period_month=period_month, category_key=category_key,
            quantity=quantity, unit=unit, amount=amount, currency=currency, notes=notes,
            created_by=user.username, file=upload, confirm_duplicate=confirm_duplicate)
    except INV.InvoiceDuplicate as e:
        raise HTTPException(409, {"detail": str(e), "existing_invoice_id": e.existing_id, "kind": e.kind})
    except INV.InvoiceError as e:
        raise HTTPException(400, str(e))


@router.get("/{invoice_id}")
def detail(invoice_id: int, con=Depends(get_con), user: Auth = Depends(current_user)):
    d = INV.invoice_detail(con, invoice_id)
    if d is None:
        raise HTTPException(404, "invoice not found")
    if user.is_factory_scoped and d["facility_id"] != user.facility_id:
        raise HTTPException(403, "invoice belongs to another facility")
    if user.role == "head_office" and user.company_id is not None and d["company_id"] != user.company_id:
        raise HTTPException(403, "invoice belongs to another company")
    return {**d, "audit": INV.audit(con, invoice_id)}


@router.get("/{invoice_id}/file")
def get_file(invoice_id: int, con=Depends(get_con), user: Auth = Depends(current_user)):
    d = INV.invoice_detail(con, invoice_id)
    if d is None:
        raise HTTPException(404, "invoice not found")
    if user.is_factory_scoped and d["facility_id"] != user.facility_id:
        raise HTTPException(403, "invoice belongs to another facility")
    if not d.get("file_path"):
        raise HTTPException(404, "no document attached")
    try:
        return FileResponse(d["file_path"], media_type=d.get("file_mime") or "application/octet-stream",
                            filename=d.get("file_name") or "invoice")
    except FileNotFoundError:
        raise HTTPException(404, "document file missing on disk")


@router.post("/{invoice_id}/calculate")
def calculate(invoice_id: int, body: CalculateIn, con=Depends(get_con),
              user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    d = INV.invoice_detail(con, invoice_id)
    if d is None:
        raise HTTPException(404, "invoice not found")
    if user.is_factory_scoped and d["facility_id"] != user.facility_id:
        raise HTTPException(403, "invoice belongs to another facility")
    try:
        return INV.calculate_invoice(
            con, invoice_id, user=user.username, factor_id=body.factor_id,
            factor_version=body.factor_version,
            ownership_control=body.ownership_control, energy_purchased=body.energy_purchased,
            value_chain_relation=body.value_chain_relation)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except INV.InvoiceError as e:
        raise HTTPException(400, str(e))


@router.post("/{invoice_id}/void")
def void(invoice_id: int, body: VoidIn, con=Depends(get_con),
         user: Auth = Depends(require("admin", "head_office"))):
    d = INV.invoice_detail(con, invoice_id)
    if d is None:
        raise HTTPException(404, "invoice not found")
    try:
        INV.void_invoice(con, invoice_id, user=user.username, reason=body.reason)
    except INV.InvoiceError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "status": "void"}


@router.get("/{invoice_id}/audit")
def audit(invoice_id: int, con=Depends(get_con), user: Auth = Depends(current_user)):
    d = INV.invoice_detail(con, invoice_id)
    if d is None:
        raise HTTPException(404, "invoice not found")
    if user.is_factory_scoped and d["facility_id"] != user.facility_id:
        raise HTTPException(403, "invoice belongs to another facility")
    return INV.audit(con, invoice_id)
