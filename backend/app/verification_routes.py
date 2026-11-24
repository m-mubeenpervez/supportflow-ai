"""Secure customer email verification endpoint."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .db import Session
from .email_verification_service import (
    consume_verification_token,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=43, max_length=43)


@router.post("/verify-email")
async def verify_email(data: VerifyEmailRequest):
    """Verify an email using a one-time bearer challenge."""

    async with Session() as db:
        async with db.begin():
            verified = await consume_verification_token(
                db,
                raw_token=data.token,
            )

    if not verified:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification link",
        )

    return {"message": "Email verified successfully"}
