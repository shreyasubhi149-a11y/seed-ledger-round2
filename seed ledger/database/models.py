"""Database tables and relationships."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.connection import Base


# ---------------------------------------------------------
# Growers
# ---------------------------------------------------------

class Grower(Base):
    __tablename__ = "growers"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)

    email = Column(
        String,
        unique=True,
        index=True,
        nullable=True,
    )

    location = Column(String, nullable=True)
    bio = Column(Text, nullable=True)

    joined_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    seed_lots = relationship(
        "SeedLot",
        back_populates="owner",
        foreign_keys="SeedLot.owner_id",
    )

    quality_reports = relationship(
        "QualityReport",
        back_populates="reporter",
    )

    exchanges_sent = relationship(
        "Exchange",
        back_populates="from_grower",
        foreign_keys="Exchange.from_grower_id",
    )

    exchanges_received = relationship(
        "Exchange",
        back_populates="to_grower",
        foreign_keys="Exchange.to_grower_id",
    )


# ---------------------------------------------------------
# Seed batches
# ---------------------------------------------------------

class SeedLot(Base):
    __tablename__ = "seed_lots"

    id = Column(Integer, primary_key=True, index=True)

    owner_id = Column(
        Integer,
        ForeignKey("growers.id"),
        nullable=False,
    )

    variety = Column(String, nullable=False)
    species = Column(String, nullable=True)
    source = Column(String, nullable=True)

    date_saved = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    description = Column(Text, nullable=True)

    generation = Column(
        Integer,
        default=1,
    )

    parent_lot_id = Column(
        Integer,
        ForeignKey("seed_lots.id"),
        nullable=True,
    )

    available_seeds = Column(
        Integer,
        nullable=False,
        default=0,
    )

    storage_location = Column(
        String,
        nullable=True,
    )

    pollination = Column(
        String,
        nullable=False,
        default="unknown",
    )

    is_available = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    owner = relationship(
        "Grower",
        back_populates="seed_lots",
        foreign_keys=[owner_id],
    )

    parent_lot = relationship(
        "SeedLot",
        remote_side=[id],
    )

    quality_reports = relationship(
        "QualityReport",
        back_populates="seed_lot",
        cascade="all, delete-orphan",
    )

    exchanges = relationship(
        "Exchange",
        back_populates="seed_lot",
    )


# ---------------------------------------------------------
# Quality observations
# ---------------------------------------------------------

class QualityReport(Base):
    __tablename__ = "quality_reports"

    id = Column(Integer, primary_key=True, index=True)

    seed_lot_id = Column(
        Integer,
        ForeignKey("seed_lots.id"),
        nullable=False,
    )

    reporter_id = Column(
        Integer,
        ForeignKey("growers.id"),
        nullable=False,
    )

    germination_rate = Column(Float, nullable=True)
    purity_rating = Column(Integer, nullable=True)
    trueness_to_type = Column(Integer, nullable=True)

    notes = Column(Text, nullable=True)

    reported_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    seed_lot = relationship(
        "SeedLot",
        back_populates="quality_reports",
    )

    reporter = relationship(
        "Grower",
        back_populates="quality_reports",
    )


# ---------------------------------------------------------
# Completed exchanges
# ---------------------------------------------------------

class Exchange(Base):
    __tablename__ = "exchanges"

    id = Column(Integer, primary_key=True, index=True)

    seed_lot_id = Column(
        Integer,
        ForeignKey("seed_lots.id"),
        nullable=False,
    )

    from_grower_id = Column(
        Integer,
        ForeignKey("growers.id"),
        nullable=False,
    )

    to_grower_id = Column(
        Integer,
        ForeignKey("growers.id"),
        nullable=False,
    )

    quantity = Column(String, nullable=True)

    exchange_date = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    seed_lot = relationship(
        "SeedLot",
        back_populates="exchanges",
    )

    from_grower = relationship(
        "Grower",
        back_populates="exchanges_sent",
        foreign_keys=[from_grower_id],
    )

    to_grower = relationship(
        "Grower",
        back_populates="exchanges_received",
        foreign_keys=[to_grower_id],
    )


# ---------------------------------------------------------
# Login accounts
# ---------------------------------------------------------

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)

    grower_id = Column(
        Integer,
        ForeignKey("growers.id"),
        unique=True,
        nullable=False,
    )

    email = Column(
        String,
        unique=True,
        nullable=False,
    )

    password_hash = Column(
        String,
        nullable=False,
    )


class LoginSession(Base):
    __tablename__ = "login_sessions"

    token_hash = Column(
        String,
        primary_key=True,
    )

    account_id = Column(
        Integer,
        ForeignKey("accounts.id"),
        nullable=False,
    )

    expires_at = Column(
        DateTime,
        nullable=False,
    )


# ---------------------------------------------------------
# Exchange requests
# ---------------------------------------------------------

class SeedRequest(Base):
    __tablename__ = "seed_requests"

    id = Column(Integer, primary_key=True)

    seed_lot_id = Column(
        Integer,
        ForeignKey("seed_lots.id"),
        nullable=False,
    )

    requester_id = Column(
        Integer,
        ForeignKey("growers.id"),
        nullable=False,
    )

    quantity = Column(Integer, nullable=False)
    message = Column(Text, nullable=True)

    status = Column(
        String,
        nullable=False,
        default="pending",
    )

    decision_note = Column(Text, nullable=True)

    received_lot_id = Column(
        Integer,
        ForeignKey("seed_lots.id"),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        server_default=func.now(),
    )


# ---------------------------------------------------------
# Activity history
# ---------------------------------------------------------

class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)

    actor_id = Column(
        Integer,
        ForeignKey("growers.id"),
        nullable=False,
    )

    kind = Column(String, nullable=False)
    description = Column(Text, nullable=False)

    created_at = Column(
        DateTime,
        server_default=func.now(),
    )


# ---------------------------------------------------------
# Onboarding choices
# ---------------------------------------------------------

class GrowerProfile(Base):
    __tablename__ = "grower_profiles"

    grower_id = Column(
        Integer,
        ForeignKey("growers.id"),
        primary_key=True,
    )

    choices_json = Column(
        Text,
        nullable=False,
    )