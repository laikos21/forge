"""Comparison workspace: subjects x user-defined dimensions."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Comparison, ComparisonCell, ComparisonDimension, ComparisonSubject
from ..schemas import (
    CellUpsert,
    ComparisonCreate,
    ComparisonSubjectCreate,
    ComparisonUpdate,
    DimensionCreate,
    DimensionUpdate,
)
from ..services import export as export_service
from ..services import refs

router = APIRouter(prefix="/api/comparisons", tags=["comparisons"])


def _get(session: Session, comparison_id: str) -> Comparison:
    comparison = session.get(Comparison, comparison_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return comparison


def _payload(session: Session, comparison: Comparison) -> dict[str, Any]:
    subjects = sorted(comparison.subjects, key=lambda s: s.position)
    dimensions = sorted(comparison.dimensions, key=lambda d: d.position)
    cells = {
        (cell.subject_id, cell.dimension_id): {
            "id": cell.id,
            "text_value": cell.text_value,
            "numeric_value": str(cell.numeric_value) if cell.numeric_value is not None else None,
            "boolean_value": cell.boolean_value,
            "excerpt_id": cell.excerpt_id,
            "origin": cell.origin,
        }
        for cell in comparison.cells
    }

    rankings: dict[str, list[str]] = {}
    for dimension in dimensions:
        if dimension.kind not in {"number", "rating"}:
            continue
        values = [
            (subject.id, comparison_cell["numeric_value"])
            for subject in subjects
            if (comparison_cell := cells.get((subject.id, dimension.id))) is not None
            and comparison_cell["numeric_value"] is not None
        ]
        if len(values) < 2:
            continue
        ordered = sorted(values, key=lambda item: float(item[1]), reverse=dimension.higher_is_better)
        rankings[dimension.id] = [subject_id for subject_id, _ in ordered]

    return {
        "id": comparison.id,
        "title": comparison.title,
        "subject_type": comparison.subject_type,
        "description": comparison.description,
        "is_demo": comparison.is_demo,
        "updated_at": comparison.updated_at.isoformat(),
        "subjects": [
            {
                "id": subject.id,
                "position": subject.position,
                "label": subject.label,
                **refs.describe(session, subject.target_type, subject.target_id).as_dict(),
            }
            for subject in subjects
        ],
        "dimensions": [
            {
                "id": dimension.id,
                "name": dimension.name,
                "kind": dimension.kind,
                "unit": dimension.unit,
                "higher_is_better": dimension.higher_is_better,
                "weight": str(dimension.weight),
                "position": dimension.position,
            }
            for dimension in dimensions
        ],
        "cells": {f"{subject_id}:{dimension_id}": value for (subject_id, dimension_id), value in cells.items()},
        "rankings": rankings,
    }


@router.get("")
def list_comparisons(session: Annotated[Session, Depends(get_db)]) -> dict:
    rows = session.execute(select(Comparison).order_by(Comparison.updated_at.desc())).scalars().all()
    return {
        "items": [
            {
                "id": c.id,
                "title": c.title,
                "subject_type": c.subject_type,
                "description": c.description,
                "is_demo": c.is_demo,
                "updated_at": c.updated_at.isoformat(),
                "subject_count": len(c.subjects),
                "dimension_count": len(c.dimensions),
            }
            for c in rows
        ],
        "total": len(rows),
    }


@router.post("", status_code=201)
def create_comparison(payload: ComparisonCreate, session: Annotated[Session, Depends(get_db)]) -> dict:
    comparison = Comparison(
        title=payload.title,
        subject_type=payload.subject_type.value,
        description=payload.description,
    )
    session.add(comparison)
    session.flush()
    for position, name in enumerate(payload.dimensions):
        session.add(ComparisonDimension(comparison_id=comparison.id, name=name, position=position))
    session.flush()
    session.refresh(comparison)
    return _payload(session, comparison)


@router.get("/{comparison_id}")
def get_comparison(comparison_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    return _payload(session, _get(session, comparison_id))


@router.patch("/{comparison_id}")
def update_comparison(
    comparison_id: str,
    payload: ComparisonUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    comparison = _get(session, comparison_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(comparison, field, value)
    session.flush()
    return _payload(session, comparison)


@router.delete("/{comparison_id}")
def delete_comparison(comparison_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    comparison = _get(session, comparison_id)
    session.delete(comparison)
    return {"deleted": comparison_id}


@router.post("/{comparison_id}/subjects", status_code=201)
def add_subject(
    comparison_id: str,
    payload: ComparisonSubjectCreate,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    comparison = _get(session, comparison_id)
    info = refs.describe(session, payload.target_type.value, payload.target_id)
    if not info.exists:
        raise HTTPException(status_code=422, detail="Subject object does not exist")
    existing = session.execute(
        select(ComparisonSubject).where(
            ComparisonSubject.comparison_id == comparison_id,
            ComparisonSubject.target_type == payload.target_type.value,
            ComparisonSubject.target_id == payload.target_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _payload(session, comparison)
    position = int(
        session.execute(
            select(func.coalesce(func.max(ComparisonSubject.position), -1)).where(
                ComparisonSubject.comparison_id == comparison_id
            )
        ).scalar_one()
        + 1
    )
    session.add(
        ComparisonSubject(
            comparison_id=comparison_id,
            target_type=payload.target_type.value,
            target_id=payload.target_id,
            label=payload.label or info.label,
            position=position,
        )
    )
    session.flush()
    session.refresh(comparison)
    return _payload(session, comparison)


@router.delete("/{comparison_id}/subjects/{subject_id}")
def remove_subject(
    comparison_id: str,
    subject_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    comparison = _get(session, comparison_id)
    subject = session.get(ComparisonSubject, subject_id)
    if subject is None or subject.comparison_id != comparison_id:
        raise HTTPException(status_code=404, detail="Subject not found")
    session.delete(subject)
    session.flush()
    session.refresh(comparison)
    return _payload(session, comparison)


@router.post("/{comparison_id}/dimensions", status_code=201)
def add_dimension(
    comparison_id: str,
    payload: DimensionCreate,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    comparison = _get(session, comparison_id)
    position = int(
        session.execute(
            select(func.coalesce(func.max(ComparisonDimension.position), -1)).where(
                ComparisonDimension.comparison_id == comparison_id
            )
        ).scalar_one()
        + 1
    )
    session.add(
        ComparisonDimension(
            comparison_id=comparison_id,
            name=payload.name,
            kind=payload.kind.value,
            unit=payload.unit,
            higher_is_better=payload.higher_is_better,
            weight=payload.weight,
            position=position,
        )
    )
    session.flush()
    session.refresh(comparison)
    return _payload(session, comparison)


@router.patch("/{comparison_id}/dimensions/{dimension_id}")
def update_dimension(
    comparison_id: str,
    dimension_id: str,
    payload: DimensionUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    comparison = _get(session, comparison_id)
    dimension = session.get(ComparisonDimension, dimension_id)
    if dimension is None or dimension.comparison_id != comparison_id:
        raise HTTPException(status_code=404, detail="Dimension not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(dimension, field, value.value if hasattr(value, "value") else value)
    session.flush()
    session.refresh(comparison)
    return _payload(session, comparison)


@router.delete("/{comparison_id}/dimensions/{dimension_id}")
def delete_dimension(
    comparison_id: str,
    dimension_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    comparison = _get(session, comparison_id)
    dimension = session.get(ComparisonDimension, dimension_id)
    if dimension is None or dimension.comparison_id != comparison_id:
        raise HTTPException(status_code=404, detail="Dimension not found")
    session.delete(dimension)
    session.flush()
    session.refresh(comparison)
    return _payload(session, comparison)


@router.put("/{comparison_id}/cells")
def upsert_cell(
    comparison_id: str,
    payload: CellUpsert,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    comparison = _get(session, comparison_id)
    subject = session.get(ComparisonSubject, payload.subject_id)
    dimension = session.get(ComparisonDimension, payload.dimension_id)
    if subject is None or subject.comparison_id != comparison_id:
        raise HTTPException(status_code=422, detail="Subject does not belong to this comparison")
    if dimension is None or dimension.comparison_id != comparison_id:
        raise HTTPException(status_code=422, detail="Dimension does not belong to this comparison")

    cell = session.execute(
        select(ComparisonCell).where(
            ComparisonCell.subject_id == payload.subject_id,
            ComparisonCell.dimension_id == payload.dimension_id,
        )
    ).scalar_one_or_none()
    if cell is None:
        cell = ComparisonCell(
            comparison_id=comparison_id,
            subject_id=payload.subject_id,
            dimension_id=payload.dimension_id,
        )
        session.add(cell)
    cell.text_value = payload.text_value
    cell.numeric_value = payload.numeric_value
    cell.boolean_value = payload.boolean_value
    cell.excerpt_id = payload.excerpt_id
    cell.origin = payload.origin
    session.flush()
    session.refresh(comparison)
    return _payload(session, comparison)


@router.get("/{comparison_id}/export/markdown")
def export_comparison(comparison_id: str, session: Annotated[Session, Depends(get_db)]) -> Response:
    comparison = _get(session, comparison_id)
    markdown = export_service.render_comparison(session, comparison)
    from ..lib.text import slugify

    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{slugify(comparison.title)}.md"'},
    )
