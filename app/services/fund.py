from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import DomainError
from app.models import FundAccount, FundEntry


def post_entry(
    session: Session, operation: str, booking_id: str, kind: str, signed_amount: int, now: float
) -> None:
    if signed_amount == 0:
        return
    account = session.scalar(select(FundAccount).where(FundAccount.id == 1).with_for_update())
    existing = session.scalar(select(FundEntry).where(FundEntry.operation_id == operation))
    if existing:
        if existing.amount_signed_vnd != signed_amount:
            raise DomainError("FUND_OPERATION_MISMATCH", status=500)
        return
    if account.balance_vnd + signed_amount < 0:
        raise DomainError("GUARANTEE_FUND_INSUFFICIENT", status=503)
    account.balance_vnd += signed_amount
    session.add(
        FundEntry(
            booking_id=booking_id,
            entry_type=kind,
            operation_id=operation,
            amount_signed_vnd=signed_amount,
            balance_after_vnd=account.balance_vnd,
            created_at=now,
        )
    )
