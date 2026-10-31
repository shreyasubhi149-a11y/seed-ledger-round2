"""Business logic used by the API routes."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from database import models as m
from database import crud
from backend import schemas as s


# ---------------------------------------------------------
# Common helpers
# ---------------------------------------------------------

def require(db, model, record_id, label):
    """Return a record or raise a clear not-found error."""
    record = db.get(model, record_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"{label} not found",
        )

    return record


def activity(db, actor, kind, description):
    """Add an activity record to the current transaction."""
    db.add(
        m.Activity(
            actor_id=actor,
            kind=kind,
            description=description,
        )
    )


def lot_view(db, lot):
    """Return a seed lot with grower and quality information."""
    summary = crud.seed_lot_quality_summary(db, lot.id)

    return {
        **s.SeedLotOut.model_validate(lot).model_dump(),
        "owner_name": lot.owner.name,
        "location": lot.owner.location,
        **summary,
    }


# ---------------------------------------------------------
# Seed lot registration
# ---------------------------------------------------------

def create_lot(
    data: s.SeedLotCreate,
    account=None,
    db: Session = None,
):
    if data.owner_id != account.grower_id:
        raise HTTPException(
            status_code=403,
            detail="You can only register your own seed lots",
        )

    if not data.variety.strip():
        raise HTTPException(
            status_code=422,
            detail="Variety cannot be blank",
        )

    if data.parent_lot_id:
        parent = require(
            db,
            m.SeedLot,
            data.parent_lot_id,
            "Parent lot",
        )

        if parent.owner_id != account.grower_id:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Choose a parent lot you own. "
                    "Receive a seed transfer first."
                ),
            )

        if (
            data.variety.strip().lower()
            != parent.variety.strip().lower()
        ):
            raise HTTPException(
                status_code=422,
                detail="A child lot must keep the parent variety",
            )

        if data.generation != parent.generation + 1:
            raise HTTPException(
                status_code=422,
                detail=(
                    "A new harvest must be one generation "
                    "after its parent"
                ),
            )

    lot = m.SeedLot(**data.model_dump())

    db.add(lot)
    db.flush()

    activity(
        db,
        account.grower_id,
        "harvest",
        f"Registered {lot.variety} (lot {lot.id})",
    )

    db.commit()

    return lot_view(db, lot)


# ---------------------------------------------------------
# Inventory management
# ---------------------------------------------------------

def stock(
    id: int,
    data: s.StockUpdate,
    account=None,
    db: Session = None,
):
    lot = require(db, m.SeedLot, id, "Seed lot")

    if lot.owner_id != account.grower_id:
        raise HTTPException(
            status_code=403,
            detail="Only the owner can update inventory",
        )

    for key, value in data.model_dump().items():
        setattr(lot, key, value)

    activity(
        db,
        account.grower_id,
        "stock",
        (
            f"Updated lot {id} inventory "
            f"to {data.available_seeds} seeds"
        ),
    )

    db.commit()

    return lot_view(db, lot)


# ---------------------------------------------------------
# Quality observations
# ---------------------------------------------------------

def report(
    id: int,
    data: s.QualityReportCreate,
    account=None,
    db: Session = None,
):
    lot = require(db, m.SeedLot, id, "Seed lot")

    if data.reporter_id != account.grower_id:
        raise HTTPException(
            status_code=403,
            detail="Report under your own account",
        )

    measurements = [
        data.germination_rate,
        data.purity_rating,
        data.trueness_to_type,
    ]

    if all(value is None for value in measurements):
        raise HTTPException(
            status_code=422,
            detail="Add at least one measured or rated value",
        )

    if lot.owner_id != account.grower_id:
        raise HTTPException(
            status_code=403,
            detail=(
                "Submit observations for lots you own, "
                "including lots received through exchanges"
            ),
        )

    record = m.QualityReport(
        seed_lot_id=id,
        **data.model_dump(),
    )

    db.add(record)

    activity(
        db,
        account.grower_id,
        "quality",
        (
            f"Added quality observations for "
            f"{lot.variety} (lot {id})"
        ),
    )

    db.commit()
    db.refresh(record)

    return s.QualityReportOut.model_validate(record)


# ---------------------------------------------------------
# Create exchange request
# ---------------------------------------------------------

def request_seeds(
    data: s.RequestIn,
    account=None,
    db: Session = None,
):
    lot = require(
        db,
        m.SeedLot,
        data.seed_lot_id,
        "Seed lot",
    )

    if lot.owner_id == account.grower_id:
        raise HTTPException(
            status_code=400,
            detail="Choose another grower's lot",
        )

    if (
        not lot.is_available
        or lot.available_seeds < data.quantity
    ):
        raise HTTPException(
            status_code=409,
            detail="Not enough available seeds",
        )

    existing = (
        db.query(m.SeedRequest)
        .filter_by(
            seed_lot_id=lot.id,
            requester_id=account.grower_id,
            status="pending",
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="You already have a pending request for this lot",
        )

    request = m.SeedRequest(
        requester_id=account.grower_id,
        **data.model_dump(),
    )

    db.add(request)
    db.flush()

    activity(
        db,
        account.grower_id,
        "request",
        f"Requested {data.quantity} seeds of {lot.variety}",
    )

    db.commit()

    return {
        "id": request.id,
        "status": request.status,
    }


def request_view(db, request):
    """Prepare an exchange request for the frontend."""
    lot = require(
        db,
        m.SeedLot,
        request.seed_lot_id,
        "Seed lot",
    )

    requester = require(
        db,
        m.Grower,
        request.requester_id,
        "Requester",
    )

    return {
        "id": request.id,
        "seed_lot_id": request.seed_lot_id,
        "variety": lot.variety,
        "owner_id": lot.owner_id,
        "owner_name": lot.owner.name,
        "requester_id": request.requester_id,
        "requester_name": requester.name,
        "quantity": request.quantity,
        "message": request.message,
        "status": request.status,
        "decision_note": request.decision_note,
        "received_lot_id": request.received_lot_id,
        "created_at": request.created_at,
    }


# ---------------------------------------------------------
# Approve, reject or cancel a request
# ---------------------------------------------------------

def decision(
    id: int,
    data: s.Decision,
    account=None,
    db: Session = None,
):
    request = require(
        db,
        m.SeedRequest,
        id,
        "Request",
    )

    lot = require(
        db,
        m.SeedLot,
        request.seed_lot_id,
        "Seed lot",
    )

    actor = account.grower_id

    if data.action == "cancel":
        if actor != request.requester_id:
            raise HTTPException(
                status_code=403,
                detail="Only the requester can cancel",
            )

    elif actor != lot.owner_id:
        raise HTTPException(
            status_code=403,
            detail="Only the current lot owner can decide",
        )

    target_status = {
        "approve": "approved",
        "reject": "rejected",
        "cancel": "cancelled",
    }[data.action]

    # Only one operation can change a pending request.
    claimed = db.execute(
        update(m.SeedRequest)
        .where(
            m.SeedRequest.id == id,
            m.SeedRequest.status == "pending",
        )
        .values(
            status=target_status,
            decision_note=data.note,
        )
    )

    if claimed.rowcount != 1:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="This request has already been decided",
        )

    if data.action == "approve":
        # Check and deduct inventory in one database operation.
        changed = db.execute(
            update(m.SeedLot)
            .where(
                m.SeedLot.id == lot.id,
                m.SeedLot.is_available.is_(True),
                m.SeedLot.available_seeds >= request.quantity,
            )
            .values(
                available_seeds=(
                    m.SeedLot.available_seeds - request.quantity
                )
            )
        )

        if changed.rowcount != 1:
            # Undo the request decision as well.
            db.rollback()

            raise HTTPException(
                status_code=409,
                detail=(
                    "Stock changed. Update stock "
                    "or reject the request."
                ),
            )

        received_lot = m.SeedLot(
            owner_id=request.requester_id,
            variety=lot.variety,
            species=lot.species,
            source=f"Transfer from lot {lot.id}",
            pollination=lot.pollination,
            date_saved=lot.date_saved,
            generation=lot.generation,
            parent_lot_id=lot.id,
            available_seeds=request.quantity,
            is_available=True,
            description=(
                "Received seed portion. Generation remains "
                "unchanged until a new harvest."
            ),
        )

        db.add(received_lot)
        db.flush()

        request.received_lot_id = received_lot.id

        db.add(
            m.Exchange(
                seed_lot_id=lot.id,
                from_grower_id=lot.owner_id,
                to_grower_id=request.requester_id,
                quantity=f"{request.quantity} seeds",
                exchange_date=datetime.now(timezone.utc),
                notes=(
                    f"Approved request #{id}. "
                    f"Received lot #{received_lot.id}"
                ),
            )
        )

    activity(
        db,
        actor,
        "exchange",
        (
            f"{target_status.capitalize()} request #{id} "
            f"for {request.quantity} seeds of {lot.variety}"
        ),
    )

    db.commit()
    db.refresh(request)

    return request_view(db, request)


# ---------------------------------------------------------
# Conservation Watch
# ---------------------------------------------------------

def insights(db: Session = None):
    all_lots = db.query(m.SeedLot).all()

    groups = {}
    alerts = []

    for lot in all_lots:
        groups.setdefault(lot.variety, []).append(lot)

    # Review varieties held by fewer than two growers.
    for variety, lots in groups.items():
        holders = {
            lot.owner_id
            for lot in lots
            if lot.available_seeds > 0
        }

        if len(holders) < 2:
            alerts.append(
                {
                    "level": "attention",
                    "title": "Conservation coverage",
                    "variety": variety,
                    "detail": (
                        f"{len(holders)} grower(s) report "
                        "remaining stock. Consider "
                        "distributing a backup."
                    ),
                }
            )

    for lot in all_lots:
        summary = crud.seed_lot_quality_summary(db, lot.id)

        if not summary["report_count"]:
            alerts.append(
                {
                    "level": "review",
                    "title": "Quality evidence missing",
                    "variety": lot.variety,
                    "lot_id": lot.id,
                    "detail": (
                        "No quality observations recorded "
                        "for this lot. Test a sample "
                        "before sharing."
                    ),
                }
            )

        elif (
            summary["avg_germination_rate"] is not None
            and summary["avg_germination_rate"] < 70
        ):
            alerts.append(
                {
                    "level": "attention",
                    "title": "Germination review",
                    "variety": lot.variety,
                    "lot_id": lot.id,
                    "detail": (
                        "Reported average is below the "
                        "demo review threshold of 70%. "
                        "Retest a sample."
                    ),
                }
            )

        if lot.date_saved:
            saved_at = lot.date_saved.replace(tzinfo=None)

            if (datetime.now() - saved_at).days > 365:
                alerts.append(
                    {
                        "level": "review",
                        "title": "Storage review due",
                        "variety": lot.variety,
                        "lot_id": lot.id,
                        "detail": (
                            "Saved more than a year ago. "
                            "Check species-specific storage "
                            "and retest viability."
                        ),
                    }
                )

    return {
        "alerts": alerts,
        "method": (
            "Transparent demonstration thresholds, not "
            "agronomic advice or laboratory certification. "
            "Empty stock does not prove a variety is extinct."
        ),
    }


# ---------------------------------------------------------
# Rule-based seed matching
# ---------------------------------------------------------

def matches(
    q: str = "",
    location: str = "",
    account=None,
    db: Session = None,
):
    results = []

    available_lots = (
        db.query(m.SeedLot)
        .filter(
            m.SeedLot.available_seeds > 0,
            m.SeedLot.is_available.is_(True),
            m.SeedLot.owner_id != account.grower_id,
        )
        .all()
    )

    query = q.strip().lower()
    location_query = location.strip().lower()

    for lot in available_lots:
        searchable_text = (
            f"{lot.variety} {lot.species or ''}"
        ).lower()

        if query and query not in searchable_text:
            continue

        quality = crud.seed_lot_quality_summary(db, lot.id)

        score = 0
        reasons = []

        if (
            location_query
            and location_query in (lot.owner.location or "").lower()
        ):
            score += 30
            reasons.append(
                "Location text matches your search (+30)"
            )

        if quality["avg_germination_rate"] is not None:
            score += round(
                quality["avg_germination_rate"] * 0.5,
                1,
            )

            reasons.append(
                "Reported germination contributes up to 50 points"
            )

        if quality["report_count"]:
            score += min(quality["report_count"], 4) * 5

            reasons.append(
                "Evidence count contributes up to 20 points"
            )

        results.append(
            {
                **lot_view(db, lot),
                "match_score": score,
                "reasons": reasons or [
                    "Available inventory, no quality evidence yet"
                ],
            }
        )

    return {
        "method": (
            "Rule-based ranking, maximum 100. "
            "No trained AI or climate suitability prediction. "
            "Location matching uses text, not GPS distance."
        ),
        "results": sorted(
            results,
            key=lambda item: item["match_score"],
            reverse=True,
        ),
    }