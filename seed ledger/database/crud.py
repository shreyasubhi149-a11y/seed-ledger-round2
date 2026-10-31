"""Database query and aggregate helpers."""

from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import models
from backend import schemas


# ---------------------------------------------------------
# Growers
# ---------------------------------------------------------

def create_grower(
    db: Session,
    grower: schemas.GrowerCreate,
) -> models.Grower:
    record = models.Grower(**grower.model_dump())

    db.add(record)
    db.commit()
    db.refresh(record)

    return record


def get_grower(
    db: Session,
    grower_id: int,
) -> Optional[models.Grower]:
    return db.get(models.Grower, grower_id)


def list_growers(
    db: Session,
    skip: int = 0,
    limit: int = 100,
) -> List[models.Grower]:
    return (
        db.query(models.Grower)
        .order_by(models.Grower.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def grower_reputation(
    db: Session,
    grower_id: int,
) -> Optional[float]:
    """Calculate a community signal from submitted observations."""
    reports = (
        db.query(models.QualityReport)
        .join(
            models.SeedLot,
            models.QualityReport.seed_lot_id == models.SeedLot.id,
        )
        .filter(models.SeedLot.owner_id == grower_id)
        .all()
    )

    scores = []

    for report in reports:
        parts = []

        if report.germination_rate is not None:
            parts.append(report.germination_rate)

        if report.purity_rating is not None:
            parts.append(report.purity_rating * 20)

        if report.trueness_to_type is not None:
            parts.append(report.trueness_to_type * 20)

        if parts:
            scores.append(sum(parts) / len(parts))

    if not scores:
        return None

    return round(sum(scores) / len(scores), 1)


# ---------------------------------------------------------
# Seed lots
# ---------------------------------------------------------

def create_seed_lot(
    db: Session,
    lot: schemas.SeedLotCreate,
) -> models.SeedLot:
    record = models.SeedLot(**lot.model_dump())

    db.add(record)
    db.commit()
    db.refresh(record)

    return record


def get_seed_lot(
    db: Session,
    lot_id: int,
) -> Optional[models.SeedLot]:
    return db.get(models.SeedLot, lot_id)


def list_seed_lots(
    db: Session,
    variety: Optional[str] = None,
    species: Optional[str] = None,
    owner_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[models.SeedLot]:
    query = db.query(models.SeedLot)

    if variety:
        query = query.filter(
            models.SeedLot.variety.ilike(f"%{variety}%")
        )

    if species:
        query = query.filter(
            models.SeedLot.species.ilike(f"%{species}%")
        )

    if owner_id is not None:
        query = query.filter(
            models.SeedLot.owner_id == owner_id
        )

    return (
        query.order_by(models.SeedLot.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def seed_lot_quality_summary(
    db: Session,
    lot_id: int,
) -> dict:
    row = (
        db.query(
            func.avg(models.QualityReport.germination_rate),
            func.avg(models.QualityReport.purity_rating),
            func.avg(models.QualityReport.trueness_to_type),
            func.count(models.QualityReport.id),
        )
        .filter(
            models.QualityReport.seed_lot_id == lot_id
        )
        .one()
    )

    average_germination, average_purity, average_trueness, count = row

    exchange_count = (
        db.query(func.count(models.Exchange.id))
        .filter(models.Exchange.seed_lot_id == lot_id)
        .scalar()
    )

    return {
        "avg_germination_rate": (
            round(average_germination, 1)
            if average_germination is not None
            else None
        ),
        "avg_purity_rating": (
            round(average_purity, 1)
            if average_purity is not None
            else None
        ),
        "avg_trueness_to_type": (
            round(average_trueness, 1)
            if average_trueness is not None
            else None
        ),
        "report_count": count or 0,
        "exchange_count": exchange_count or 0,
    }


def get_lot_lineage(
    db: Session,
    lot_id: int,
) -> List[models.SeedLot]:
    """Follow parent links back to the original seed lot."""
    lineage = []
    seen = set()

    current = get_seed_lot(db, lot_id)

    while current is not None and current.id not in seen:
        lineage.append(current)
        seen.add(current.id)

        current = (
            get_seed_lot(db, current.parent_lot_id)
            if current.parent_lot_id
            else None
        )

    return lineage


# ---------------------------------------------------------
# Quality reports
# ---------------------------------------------------------

def create_quality_report(
    db: Session,
    lot_id: int,
    report: schemas.QualityReportCreate,
) -> models.QualityReport:
    record = models.QualityReport(
        seed_lot_id=lot_id,
        **report.model_dump(),
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return record


def list_quality_reports(
    db: Session,
    lot_id: int,
) -> List[models.QualityReport]:
    return (
        db.query(models.QualityReport)
        .filter(models.QualityReport.seed_lot_id == lot_id)
        .order_by(models.QualityReport.reported_at.desc())
        .all()
    )


# ---------------------------------------------------------
# Completed exchanges
# ---------------------------------------------------------

def create_exchange(
    db: Session,
    exchange: schemas.ExchangeCreate,
) -> models.Exchange:
    record = models.Exchange(**exchange.model_dump())

    db.add(record)
    db.commit()
    db.refresh(record)

    return record


def list_exchanges(
    db: Session,
    grower_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[models.Exchange]:
    query = db.query(models.Exchange)

    if grower_id is not None:
        query = query.filter(
            (models.Exchange.from_grower_id == grower_id)
            | (models.Exchange.to_grower_id == grower_id)
        )

    return (
        query.order_by(models.Exchange.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------
# Network statistics
# ---------------------------------------------------------

def network_stats(db: Session) -> dict:
    grower_count = (
        db.query(func.count(models.Grower.id)).scalar() or 0
    )

    seed_lot_count = (
        db.query(func.count(models.SeedLot.id)).scalar() or 0
    )

    variety_count = (
        db.query(
            func.count(func.distinct(models.SeedLot.variety))
        ).scalar()
        or 0
    )

    exchange_count = (
        db.query(func.count(models.Exchange.id)).scalar() or 0
    )

    report_count = (
        db.query(func.count(models.QualityReport.id)).scalar()
        or 0
    )

    average_germination = (
        db.query(
            func.avg(models.QualityReport.germination_rate)
        ).scalar()
    )

    return {
        "grower_count": grower_count,
        "seed_lot_count": seed_lot_count,
        "variety_count": variety_count,
        "exchange_count": exchange_count,
        "quality_report_count": report_count,
        "avg_germination_rate": (
            round(average_germination, 1)
            if average_germination is not None
            else None
        ),
    }


# ---------------------------------------------------------
# Network graph
# ---------------------------------------------------------

def network_graph(db: Session) -> dict:
    growers = db.query(models.Grower).all()

    nodes = []

    for grower in growers:
        lot_count = (
            db.query(func.count(models.SeedLot.id))
            .filter(models.SeedLot.owner_id == grower.id)
            .scalar()
            or 0
        )

        nodes.append(
            {
                "id": grower.id,
                "name": grower.name,
                "seed_lot_count": lot_count,
                "reputation_score": grower_reputation(
                    db,
                    grower.id,
                ),
            }
        )

    exchanges = db.query(models.Exchange).all()
    edge_map = {}

    for exchange in exchanges:
        key = (
            exchange.from_grower_id,
            exchange.to_grower_id,
        )

        if key not in edge_map:
            edge_map[key] = {
                "count": 0,
                "lots": set(),
            }

        edge_map[key]["count"] += 1

        if exchange.seed_lot:
            edge_map[key]["lots"].add(
                exchange.seed_lot.variety
            )

    edges = [
        {
            "from_grower_id": key[0],
            "to_grower_id": key[1],
            "exchange_count": value["count"],
            "lots": sorted(value["lots"]),
        }
        for key, value in edge_map.items()
    ]

    return {
        "nodes": nodes,
        "edges": edges,
    }