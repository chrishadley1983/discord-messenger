"""Vault API Routes — Secure local storage for sensitive data (payment cards).

Encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256).
Data never leaves localhost. No logging of sensitive fields.

Endpoints:
    POST /vault/cards         — Save a new card (encrypts + writes to disk)
    GET  /vault/cards         — List cards (last-4 digits only)
    GET  /vault/cards/default — Full card details (for browser automation only)
    DELETE /vault/cards/{id}  — Remove a card
"""

import json
import os
import uuid
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/vault", tags=["Vault"])

# Encryption key from .env — generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
_VAULT_KEY = os.getenv("VAULT_ENCRYPTION_KEY", "")
_VAULT_DIR = Path(__file__).parent.parent / "data" / "vault"


def _get_fernet() -> Fernet:
    if not _VAULT_KEY:
        raise HTTPException(status_code=500, detail="VAULT_ENCRYPTION_KEY not configured")
    try:
        return Fernet(_VAULT_KEY.encode())
    except Exception:
        raise HTTPException(status_code=500, detail="Invalid VAULT_ENCRYPTION_KEY")


def _cards_path() -> Path:
    _VAULT_DIR.mkdir(parents=True, exist_ok=True)
    return _VAULT_DIR / "cards.enc"


def _read_cards() -> list[dict]:
    path = _cards_path()
    if not path.exists():
        return []
    f = _get_fernet()
    try:
        encrypted = path.read_bytes()
        decrypted = f.decrypt(encrypted)
        return json.loads(decrypted)
    except (InvalidToken, json.JSONDecodeError):
        raise HTTPException(status_code=500, detail="Vault file corrupted or key mismatch")


def _write_cards(cards: list[dict]) -> None:
    f = _get_fernet()
    plaintext = json.dumps(cards, indent=2).encode()
    encrypted = f.encrypt(plaintext)
    path = _cards_path()
    path.write_bytes(encrypted)


class CardInput(BaseModel):
    label: str = Field(description="Card label, e.g. 'Visa Personal'")
    card_number: str = Field(description="Full card number")
    expiry: str = Field(description="MM/YY format")
    cvc: str = Field(description="3 or 4 digit CVC")
    name_on_card: str = Field(default="Chris Hadley", description="Cardholder name")
    is_default: bool = Field(default=True, description="Set as default card")


class CardSummary(BaseModel):
    id: str
    label: str
    last_four: str
    expiry: str
    name_on_card: str
    is_default: bool


class CardFull(BaseModel):
    id: str
    label: str
    card_number: str
    expiry: str
    cvc: str
    name_on_card: str


@router.post("/cards", response_model=CardSummary)
async def save_card(card: CardInput):
    """Save a new payment card (encrypted at rest)."""
    cards = _read_cards()

    # If this card is default, unset others
    if card.is_default:
        for c in cards:
            c["is_default"] = False

    clean_number = card.card_number.replace(" ", "").replace("-", "")
    new_card = {
        "id": uuid.uuid4().hex[:8],
        "label": card.label,
        "card_number": clean_number,
        "expiry": card.expiry,
        "cvc": card.cvc,
        "name_on_card": card.name_on_card,
        "is_default": card.is_default,
    }
    cards.append(new_card)
    _write_cards(cards)

    return CardSummary(
        id=new_card["id"],
        label=new_card["label"],
        last_four=clean_number[-4:],
        expiry=new_card["expiry"],
        name_on_card=new_card["name_on_card"],
        is_default=new_card["is_default"],
    )


@router.get("/cards", response_model=list[CardSummary])
async def list_cards():
    """List saved cards (last 4 digits only — safe for display)."""
    cards = _read_cards()
    return [
        CardSummary(
            id=c["id"],
            label=c["label"],
            last_four=c["card_number"][-4:],
            expiry=c["expiry"],
            name_on_card=c["name_on_card"],
            is_default=c.get("is_default", False),
        )
        for c in cards
    ]


@router.get("/cards/default", response_model=CardFull)
async def get_default_card():
    """Return full card details for the default card.

    SECURITY: Only for use in browser_run_code Stripe fills.
    Never display full details in Discord or logs.
    """
    cards = _read_cards()
    default = next((c for c in cards if c.get("is_default")), None)
    if not default:
        if cards:
            default = cards[0]
        else:
            raise HTTPException(status_code=404, detail="No cards saved")

    return CardFull(
        id=default["id"],
        label=default["label"],
        card_number=default["card_number"],
        expiry=default["expiry"],
        cvc=default["cvc"],
        name_on_card=default["name_on_card"],
    )


@router.delete("/cards/{card_id}")
async def delete_card(card_id: str):
    """Remove a saved card."""
    cards = _read_cards()
    filtered = [c for c in cards if c["id"] != card_id]
    if len(filtered) == len(cards):
        raise HTTPException(status_code=404, detail="Card not found")
    _write_cards(filtered)
    return {"deleted": card_id}
