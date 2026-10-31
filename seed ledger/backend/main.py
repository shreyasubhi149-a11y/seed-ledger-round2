"""
The Seed Ledger — backend API.

Entry point:
    backend.main:app

The root-level run.py file will start this application.
"""

import csv
import hashlib
import io
import json
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import schemas as s
from backend import services
from backend.auth import (
    current_account,
    hash_password,
    new_session,
    verify_password,
)
from backend.schemas import (
    Decision,
    Login,
    ProfileChoices,
    Register,
    RequestIn,
    StockUpdate,
)
from backend.services import (
    activity,
    lot_view,
    request_view,
    require,
)
from database import crud
from database import models as m
from database.connection import get_db, initialize
from database.models import GrowerProfile


# --------------------------------------------------
# Application setup
# --------------------------------------------------

# main.py is inside backend/, so move up to the project folder.
ROOT = Path(__file__).resolve().parent.parent

# Create missing tables without deleting existing records.
initialize()

app = FastAPI(
    title="The Seed Ledger",
    version="2.0.0",
    description=(
        "Community seed sharing, quality observations, "
        "inventory and traceable exchanges. "
        "Matching uses transparent rules, not a trained AI model."
    ),
)

# Frontend CSS and JavaScript are available under /assets.
app.mount(
    "/assets",
    StaticFiles(directory=ROOT / "frontend"),
    name="assets",
)


# --------------------------------------------------
# Response headers
# --------------------------------------------------

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"

    documentation_paths = {
        "/docs",
        "/redoc",
        "/docs/oauth2-redirect",
    }

    if request.url.path not in documentation_paths:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' "
            "https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'"
        )

    return response


# --------------------------------------------------
# Database error handling
# --------------------------------------------------

@app.exception_handler(IntegrityError)
async def database_integrity_error(
    request: Request,
    error: IntegrityError,
):
    return JSONResponse(
        status_code=409,
        content={
            "detail": (
                "That record already exists or references "
                "an invalid record."
            )
        },
    )


# --------------------------------------------------
# Home page and health check
# --------------------------------------------------

@app.get("/", include_in_schema=False)
def home():
    return FileResponse(ROOT / "frontend" / "index.html")


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))

    return {
        "status": "ok",
        "version": "2.0.0",
        "database": "connected",
    }


# --------------------------------------------------
# Registration
# --------------------------------------------------

@app.post("/auth/register", status_code=201)
def register(
    data: Register,
    db: Session = Depends(get_db),
):
    email = str(data.email).lower()

    existing_grower = (
        db.query(m.Grower)
        .filter(func.lower(m.Grower.email) == email)
        .first()
    )

    if existing_grower:
        raise HTTPException(
            status_code=409,
            detail="Email already registered. Sign in instead.",
        )

    grower = m.Grower(
        name=data.name.strip(),
        email=email,
        location=data.location.strip(),
        bio=data.bio,
    )

    db.add(grower)
    db.flush()

    account = m.Account(
        grower_id=grower.id,
        email=email,
        password_hash=hash_password(data.password),
    )

    db.add(account)
    db.flush()

    activity(
        db,
        grower.id,
        "member",
        "Joined the seed network",
    )

    db.commit()

    return {
        "token": new_session(db, account.id),
        "grower_id": grower.id,
    }


# --------------------------------------------------
# Login and logout
# --------------------------------------------------

@app.post("/auth/login")
def login(
    data: Login,
    db: Session = Depends(get_db),
):
    email = str(data.email).lower()

    account = (
        db.query(m.Account)
        .filter(m.Account.email == email)
        .first()
    )

    if not account or not verify_password(
        data.password,
        account.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
        )

    return {
        "token": new_session(db, account.id),
        "grower_id": account.grower_id,
    }


@app.get("/auth/me")
def current_profile(
    account=Depends(current_account),
    db: Session = Depends(get_db),
):
    grower = require(
        db,
        m.Grower,
        account.grower_id,
        "Grower",
    )

    profile = db.get(GrowerProfile, grower.id)

    return {
        "id": grower.id,
        "name": grower.name,
        "email": grower.email,
        "location": grower.location,
        "onboarding": (
            json.loads(profile.choices_json)
            if profile
            else None
        ),
    }


@app.post("/auth/logout")
def logout(
    request: Request,
    account=Depends(current_account),
    db: Session = Depends(get_db),
):
    token = (
        request.headers.get("Authorization", "")
        .removeprefix("Bearer ")
        .strip()
    )

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = db.get(m.LoginSession, token_hash)

    if session:
        db.delete(session)
        db.commit()

    return {"ok": True}


# --------------------------------------------------
# Required seed-profile setup
# --------------------------------------------------

@app.put("/profile")
def update_profile(
    data: ProfileChoices,
    account=Depends(current_account),
    db: Session = Depends(get_db),
):
    record = db.get(
        GrowerProfile,
        account.grower_id,
    )

    payload = data.model_dump()

    if record is None:
        record = GrowerProfile(
            grower_id=account.grower_id,
            choices_json=json.dumps(payload),
        )
        db.add(record)
    else:
        record.choices_json = json.dumps(payload)

    db.commit()

    return payload


# --------------------------------------------------
# Grower directory
# --------------------------------------------------

@app.get("/growers")
def list_growers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    growers = crud.list_growers(db, skip, limit)

    # Public profiles do not expose email addresses.
    return [
        {
            "id": grower.id,
            "name": grower.name,
            "location": grower.location,
            "bio": grower.bio,
            "seed_lot_count": len(grower.seed_lots),
            "reputation_score": crud.grower_reputation(
                db,
                grower.id,
            ),
        }
        for grower in growers
    ]


@app.get("/growers/{grower_id}")
def get_grower(
    grower_id: int,
    db: Session = Depends(get_db),
):
    grower = require(
        db,
        m.Grower,
        grower_id,
        "Grower",
    )

    return {
        "id": grower.id,
        "name": grower.name,
        "location": grower.location,
        "bio": grower.bio,
        "seed_lot_count": len(grower.seed_lots),
        "reputation_score": crud.grower_reputation(
            db,
            grower.id,
        ),
    }


# --------------------------------------------------
# Seed catalogue
# --------------------------------------------------

@app.get("/seed-lots")
def list_seed_lots(
    q: str = "",
    species: str = "",
    owner_id: int | None = None,
    available: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(m.SeedLot)

    if q:
        query = query.filter(
            or_(
                m.SeedLot.variety.ilike(f"%{q}%"),
                m.SeedLot.species.ilike(f"%{q}%"),
            )
        )

    if species:
        query = query.filter(
            m.SeedLot.species.ilike(f"%{species}%")
        )

    if owner_id is not None:
        query = query.filter(
            m.SeedLot.owner_id == owner_id
        )

    if available:
        query = query.filter(
            m.SeedLot.is_available.is_(True),
            m.SeedLot.available_seeds > 0,
        )

    lots = (
        query
        .order_by(m.SeedLot.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [
        lot_view(db, lot)
        for lot in lots
    ]


@app.post("/seed-lots", status_code=201)
def create_seed_lot(
    data: s.SeedLotCreate,
    account=Depends(current_account),
    db: Session = Depends(get_db),
):
    return services.create_lot(
        data=data,
        account=account,
        db=db,
    )


@app.get("/seed-lots/{lot_id}")
def get_seed_lot(
    lot_id: int,
    db: Session = Depends(get_db),
):
    lot = require(
        db,
        m.SeedLot,
        lot_id,
        "Seed lot",
    )

    return lot_view(db, lot)


# --------------------------------------------------
# Lineage and seed passports
# --------------------------------------------------

@app.get("/seed-lots/{lot_id}/lineage")
def get_lineage(
    lot_id: int,
    db: Session = Depends(get_db),
):
    require(db, m.SeedLot, lot_id, "Seed lot")

    return [
        lot_view(db, lot)
        for lot in crud.get_lot_lineage(db, lot_id)
    ]


@app.get("/seed-lots/{lot_id}/passport")
def get_passport(
    lot_id: int,
    db: Session = Depends(get_db),
):
    lot = require(
        db,
        m.SeedLot,
        lot_id,
        "Seed lot",
    )

    return {
        "passport_code": f"SL-{lot.id:06d}",
        "lot": lot_view(db, lot),
        "lineage": [
            lot_view(db, ancestor)
            for ancestor in crud.get_lot_lineage(db, lot_id)
        ],
        "reports": crud.list_quality_reports(db, lot_id),
        "verification": (
            "Grower-submitted observations. "
            "Not laboratory certification."
        ),
    }


# --------------------------------------------------
# Inventory updates
# --------------------------------------------------

@app.patch("/seed-lots/{lot_id}/stock")
def update_stock(
    lot_id: int,
    data: StockUpdate,
    account=Depends(current_account),
    db: Session = Depends(get_db),
):
    return services.stock(
        id=lot_id,
        data=data,
        account=account,
        db=db,
    )


# --------------------------------------------------
# Quality observations
# --------------------------------------------------

@app.post(
    "/seed-lots/{lot_id}/quality-reports",
    status_code=201,
)
def add_quality_report(
    lot_id: int,
    data: s.QualityReportCreate,
    account=Depends(current_account),
    db: Session = Depends(get_db),
):
    return services.report(
        id=lot_id,
        data=data,
        account=account,
        db=db,
    )


@app.get(
    "/seed-lots/{lot_id}/quality-reports",
    response_model=list[s.QualityReportOut],
)
def list_quality_reports(
    lot_id: int,
    db: Session = Depends(get_db),
):
    require(db, m.SeedLot, lot_id, "Seed lot")

    return crud.list_quality_reports(db, lot_id)


# --------------------------------------------------
# Seed requests
# --------------------------------------------------

@app.post("/requests", status_code=201)
def create_request(
    data: RequestIn,
    account=Depends(current_account),
    db: Session = Depends(get_db),
):
    return services.request_seeds(
        data=data,
        account=account,
        db=db,
    )


@app.get("/requests")
def list_requests(
    account=Depends(current_account),
    db: Session = Depends(get_db),
):
    requests = (
        db.query(m.SeedRequest)
        .join(
            m.SeedLot,
            m.SeedRequest.seed_lot_id == m.SeedLot.id,
        )
        .filter(
            or_(
                m.SeedRequest.requester_id
                == account.grower_id,
                m.SeedLot.owner_id
                == account.grower_id,
            )
        )
        .order_by(m.SeedRequest.id.desc())
        .all()
    )

    return [
        request_view(db, request)
        for request in requests
    ]


@app.post("/requests/{request_id}/decision")
def decide_request(
    request_id: int,
    data: Decision,
    account=Depends(current_account),
    db: Session = Depends(get_db),
):
    return services.decision(
        id=request_id,
        data=data,
        account=account,
        db=db,
    )


# --------------------------------------------------
# Completed exchanges
# --------------------------------------------------

@app.get("/exchanges")
def list_exchanges(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    exchanges = (
        db.query(m.Exchange)
        .order_by(m.Exchange.id.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": exchange.id,
            "seed_lot_id": exchange.seed_lot_id,
            "variety": exchange.seed_lot.variety,
            "from_name": exchange.from_grower.name,
            "to_name": exchange.to_grower.name,
            "quantity": exchange.quantity,
            "exchange_date": exchange.exchange_date,
            "notes": exchange.notes,
        }
        for exchange in exchanges
    ]


@app.post("/exchanges")
def block_unverified_exchange():
    raise HTTPException(
        status_code=410,
        detail=(
            "Use /requests and owner approval. "
            "Direct unverified exchanges are disabled."
        ),
    )


# --------------------------------------------------
# Dashboard statistics
# --------------------------------------------------

@app.get("/network/stats")
def network_statistics(
    db: Session = Depends(get_db),
):
    result = crud.network_stats(db)

    available_seeds = (
        db.query(
            func.sum(m.SeedLot.available_seeds)
        ).scalar()
        or 0
    )

    variety_count = (
        db.query(
            func.count(
                func.distinct(m.SeedLot.variety)
            )
        ).scalar()
        or 0
    )

    pending_requests = (
        db.query(m.SeedRequest)
        .filter_by(status="pending")
        .count()
    )

    result.update(
        available_seeds=available_seeds,
        variety_count=variety_count,
        pending_requests=pending_requests,
    )

    return result


# --------------------------------------------------
# Network visualization and activity
# --------------------------------------------------

@app.get("/network/graph")
def network_graph(
    db: Session = Depends(get_db),
):
    return crud.network_graph(db)


@app.get("/activities")
def recent_activities(
    db: Session = Depends(get_db),
):
    records = (
        db.query(m.Activity)
        .order_by(m.Activity.id.desc())
        .limit(30)
        .all()
    )

    return [
        {
            "id": record.id,
            "kind": record.kind,
            "description": record.description,
            "actor": db.get(
                m.Grower,
                record.actor_id,
            ).name,
            "created_at": record.created_at,
        }
        for record in records
    ]


# --------------------------------------------------
# Conservation alerts and matching
# --------------------------------------------------

@app.get("/insights")
def conservation_insights(
    db: Session = Depends(get_db),
):
    return services.insights(db=db)


@app.get("/matches")
def find_matches(
    q: str = "",
    location: str = "",
    account=Depends(current_account),
    db: Session = Depends(get_db),
):
    return services.matches(
        q=q,
        location=location,
        account=account,
        db=db,
    )


# --------------------------------------------------
# Inventory CSV export
# --------------------------------------------------

@app.get("/exports/lots.csv")
def export_seed_inventory(
    account=Depends(current_account),
    db: Session = Depends(get_db),
):
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(
        [
            "Lot ID",
            "Variety",
            "Species",
            "Grower",
            "Location",
            "Available seeds",
            "Generation",
            "Germination %",
            "Reports",
        ]
    )

    def safe_cell(value):
        value = str(value or "")

        # Prevent spreadsheet formula execution from text fields.
        if value.startswith(
            ("=", "+", "-", "@", "\t", "\r")
        ):
            return "'" + value

        return value

    for lot in db.query(m.SeedLot).all():
        summary = crud.seed_lot_quality_summary(
            db,
            lot.id,
        )

        writer.writerow(
            [
                lot.id,
                safe_cell(lot.variety),
                safe_cell(lot.species),
                safe_cell(lot.owner.name),
                safe_cell(lot.owner.location),
                lot.available_seeds,
                lot.generation,
                summary["avg_germination_rate"],
                summary["report_count"],
            ]
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                'attachment; filename="seed-ledger.csv"'
            )
        },
    )