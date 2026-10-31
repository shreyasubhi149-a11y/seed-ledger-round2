"""Validation schemas for The Seed Ledger API."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    model_validator,
)


# =========================================================
# GROWERS
# =========================================================

class GrowerBase(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=100,
    )

    email: Optional[EmailStr] = None

    location: Optional[str] = Field(
        default=None,
        max_length=150,
    )

    bio: Optional[str] = Field(
        default=None,
        max_length=1500,
    )


class GrowerCreate(GrowerBase):
    pass


class GrowerOut(GrowerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    joined_at: datetime


class GrowerDetail(GrowerOut):
    seed_lot_count: int = 0
    reputation_score: Optional[float] = None


# =========================================================
# SEED BATCHES
# =========================================================

class SeedLotBase(BaseModel):
    variety: str = Field(
        min_length=2,
        max_length=120,
    )

    species: Optional[str] = Field(
        default=None,
        max_length=150,
    )

    source: Optional[str] = Field(
        default=None,
        max_length=150,
    )

    date_saved: Optional[datetime] = None

    description: Optional[str] = Field(
        default=None,
        max_length=2000,
    )

    generation: int = Field(
        default=1,
        ge=1,
        le=1000,
    )

    parent_lot_id: Optional[int] = None

    available_seeds: int = Field(
        default=0,
        ge=0,
        le=10_000_000,
    )

    storage_location: Optional[str] = Field(
        default=None,
        max_length=200,
    )

    pollination: Literal[
        "self",
        "cross",
        "unknown",
    ] = "unknown"

    is_available: bool = True


class SeedLotCreate(SeedLotBase):
    owner_id: int


class SeedLotOut(SeedLotBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    created_at: datetime


class SeedLotDetail(SeedLotOut):
    owner: GrowerOut

    avg_germination_rate: Optional[float] = None
    avg_purity_rating: Optional[float] = None
    avg_trueness_to_type: Optional[float] = None

    report_count: int = 0
    exchange_count: int = 0


# =========================================================
# QUALITY OBSERVATIONS
# =========================================================

class QualityReportBase(BaseModel):
    germination_rate: Optional[float] = Field(
        default=None,
        ge=0,
        le=100,
    )

    purity_rating: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
    )

    trueness_to_type: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
    )

    notes: Optional[str] = Field(
        default=None,
        max_length=2000,
    )


class QualityReportCreate(QualityReportBase):
    reporter_id: int


class QualityReportOut(QualityReportBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seed_lot_id: int
    reporter_id: int
    reported_at: datetime


# =========================================================
# COMPLETED EXCHANGES
# =========================================================

class ExchangeBase(BaseModel):
    seed_lot_id: int
    from_grower_id: int
    to_grower_id: int

    quantity: Optional[str] = None
    exchange_date: Optional[datetime] = None
    notes: Optional[str] = None


class ExchangeCreate(ExchangeBase):
    pass


class ExchangeOut(ExchangeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


# =========================================================
# NETWORK GRAPH
# =========================================================

class NetworkNode(BaseModel):
    id: int
    name: str
    seed_lot_count: int
    reputation_score: Optional[float] = None


class NetworkEdge(BaseModel):
    from_grower_id: int
    to_grower_id: int
    exchange_count: int

    lots: List[str] = Field(default_factory=list)


class NetworkGraph(BaseModel):
    nodes: List[NetworkNode]
    edges: List[NetworkEdge]


class NetworkStats(BaseModel):
    grower_count: int
    seed_lot_count: int
    exchange_count: int
    quality_report_count: int

    variety_count: int = 0
    avg_germination_rate: Optional[float] = None


# =========================================================
# ACCOUNT REGISTRATION
# =========================================================

class Register(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=100,
    )

    email: EmailStr

    password: str = Field(
        min_length=10,
        max_length=128,
    )

    location: str = Field(
        min_length=2,
        max_length=150,
    )

    bio: str = Field(
        default="",
        max_length=1500,
    )

    @model_validator(mode="after")
    def meaningful_text(self):
        if len(self.name.strip()) < 2:
            raise ValueError(
                "Name needs at least two non-space characters"
            )

        if len(self.location.strip()) < 2:
            raise ValueError(
                "Location needs at least two non-space characters"
            )

        return self


# =========================================================
# LOGIN
# =========================================================

class Login(BaseModel):
    email: EmailStr

    password: str = Field(
        max_length=128,
    )


# =========================================================
# INVENTORY UPDATE
# =========================================================

class StockUpdate(BaseModel):
    available_seeds: int = Field(
        ge=0,
        le=10_000_000,
    )

    storage_location: str = Field(
        default="",
        max_length=200,
    )

    is_available: bool = True


# =========================================================
# SEED REQUEST
# =========================================================

class RequestIn(BaseModel):
    seed_lot_id: int

    quantity: int = Field(
        gt=0,
        le=1_000_000,
    )

    message: str = Field(
        default="",
        max_length=1000,
    )


# =========================================================
# APPROVE / REJECT / CANCEL
# =========================================================

class Decision(BaseModel):
    action: Literal[
        "approve",
        "reject",
        "cancel",
    ]

    note: str = Field(
        default="",
        max_length=1000,
    )


# =========================================================
# GROWER ONBOARDING PROFILE
# =========================================================

class ProfileChoices(BaseModel):
    role: Literal[
        "home",
        "keeper",
        "educator",
        "farm",
    ]

    crops: List[
        Literal[
            "veg",
            "greens",
            "legumes",
            "grains",
            "fruit",
            "herbs",
        ]
    ] = Field(
        min_length=1,
        max_length=6,
    )

    part: Literal[
        "receive",
        "share",
        "both",
    ]

    exp: Literal[
        "new",
        "some",
        "expert",
    ]

    agree: Literal[True]