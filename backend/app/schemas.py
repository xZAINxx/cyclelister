"""API request/response models — the frozen REST contract."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import Fitment, Listing, ListingImage, Part

# Canonical condition vocabulary — AI grades, seller edits, and the eBay
# CONDITION_MAP all speak these values; the frontend maps them to labels.
ConditionGrade = Literal["new_nos", "new_other", "used", "for_parts"]


class CreateListingIn(BaseModel):
    hint: str | None = Field(default=None, max_length=200)


class PatchListingIn(BaseModel):
    title: str | None = Field(default=None, max_length=80)
    description: str | None = None
    price: float | None = Field(default=None, ge=0)
    quantity: int | None = Field(default=None, ge=0)
    condition: ConditionGrade | None = None
    condition_notes: str | None = None
    category_id: str | None = None
    item_specifics: dict[str, str] | None = None


class FitmentIn(BaseModel):
    make: str
    model: str
    year_start: int | None = None
    year_end: int | None = None
    confirmed: bool = True


class PutFitmentIn(BaseModel):
    fitments: list[FitmentIn]


class FitmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    make: str
    model: str
    year_start: int | None
    year_end: int | None
    confidence: float | None
    confirmed: bool


class PartOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    part_number_display: str | None
    brand: str | None
    part_type: str | None


class ImageOut(BaseModel):
    id: uuid.UUID
    url: str
    is_primary: bool
    order_index: int

    @classmethod
    def from_model(cls, img: ListingImage) -> "ImageOut":
        return cls(
            id=img.id,
            url=f"/api/images/{img.id}",
            is_primary=img.is_primary,
            order_index=img.order_index,
        )


class ListingOut(BaseModel):
    id: uuid.UUID
    status: str
    title: str | None
    description: str | None
    price: float | None
    quantity: int
    category_id: str | None
    item_specifics: dict | None
    condition: str | None
    condition_notes: str | None
    ai_confidence: float | None
    needs_human_review: bool
    hint: str | None
    ebay_listing_id: str | None
    part: PartOut | None
    fitment: list[FitmentOut]
    images: list[ImageOut]
    created_at: datetime

    @classmethod
    def from_model(cls, listing: Listing) -> "ListingOut":
        part: Part | None = listing.part
        fitment: list[Fitment] = part.fitment if part else []
        return cls(
            id=listing.id,
            status=listing.status,
            title=listing.title,
            description=listing.description,
            price=float(listing.price) if listing.price is not None else None,
            quantity=listing.quantity,
            category_id=listing.category_id,
            item_specifics=listing.item_specifics,
            condition=listing.condition,
            condition_notes=listing.condition_notes,
            ai_confidence=float(listing.ai_confidence) if listing.ai_confidence is not None else None,
            needs_human_review=listing.needs_human_review,
            hint=listing.hint,
            ebay_listing_id=listing.ebay_listing_id,
            part=PartOut.model_validate(part) if part else None,
            fitment=[FitmentOut.model_validate(f) for f in fitment],
            images=[ImageOut.from_model(img) for img in listing.images],
            created_at=listing.created_at,
        )


class ListingListOut(BaseModel):
    items: list[ListingOut]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    status: str
    result: dict | None
    error: str | None


class EbayStatusOut(BaseModel):
    configured: bool
    environment: str
    connected: bool
