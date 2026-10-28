from datetime import datetime
from typing import Any

from geoalchemy2 import Geography, WKBElement
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class Place(Base):
    __tablename__ = "places"
    __table_args__ = (
        UniqueConstraint("osm_type", "osm_id", name="uq_places_osm"),
        CheckConstraint("osm_type IN ('node', 'way', 'relation')", name="osm_type"),
        # Explicit GIST index (instead of geoalchemy2's implicit one) so it is visible
        # in migrations.
        Index("ix_places_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    osm_type: Mapped[str] = mapped_column(String(10))
    osm_id: Mapped[int] = mapped_column(BigInteger)
    city: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    geom: Mapped[WKBElement] = mapped_column(Geography("POINT", srid=4326, spatial_index=False))
    tags: Mapped[dict[str, str]] = mapped_column(JSONB, server_default="{}")
    wikidata: Mapped[str | None] = mapped_column(String(32))
    opening_hours: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    # Photo from Wikimedia Commons: thumbnail, file page (licence, author) and credit line.
    image_url: Mapped[str | None] = mapped_column(Text)
    image_page_url: Mapped[str | None] = mapped_column(Text)
    image_credit: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category: Mapped[Category] = relationship()


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    city: Mapped[str] = mapped_column(String(50))
    request_text: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    total_distance_m: Mapped[float | None] = mapped_column(Float)
    # The full API response, so a saved plan can be served again without recomputing.
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stops: Mapped[list["RouteStop"]] = relationship(
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="(RouteStop.day, RouteStop.position)",
    )


class RouteStop(Base):
    __tablename__ = "route_stops"
    __table_args__ = (
        UniqueConstraint("route_id", "day", "position", name="uq_route_stops_slot"),
        CheckConstraint("day >= 1", name="day_positive"),
        CheckConstraint("position >= 1", name="position_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"), index=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id", ondelete="RESTRICT"))
    day: Mapped[int] = mapped_column(SmallInteger)
    position: Mapped[int] = mapped_column(SmallInteger)

    route: Mapped[Route] = relationship(back_populates="stops")
    place: Mapped[Place] = relationship()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Stored lowercase: log-ins ignore case.
    email: Mapped[str] = mapped_column(String(254), unique=True)
    # argon2id, in the PHC string format (algorithm, parameters and salt included).
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSession(Base):
    """A log-in. The cookie holds a random token; only its SHA-256 is stored, so a leaked
    table cannot be replayed."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Trip(Base):
    """A plan a user saved. `plan_id` is its current version: edits make new versions
    (routes whose params name a `parent_id`), and saving one moves the trip to it."""

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    plan_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TripVisit(Base):
    """A stop of a trip the traveller has visited. Visits live on the trip, not on a plan
    version: no version the trip switches to may leave a visited place out."""

    __tablename__ = "trip_visits"

    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"), primary_key=True
    )
    place_id: Mapped[int] = mapped_column(
        ForeignKey("places.id", ondelete="RESTRICT"), primary_key=True
    )
    visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
