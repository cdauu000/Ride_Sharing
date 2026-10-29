from pathlib import Path

from fastapi.testclient import TestClient

from app.models import FundAccount
from scripts.acceptance_evidence import collect


def test_evidence_detects_fund_mismatch(client: TestClient) -> None:
    context = client.app.state.context
    database = Path(context.db.engine.url.database)
    journal = Path(context.settings.escrow_journal_path)
    result = collect(database, journal)
    assert result["fund_balanced"] and result["all_payouts_balanced"]
    with context.db.transaction() as session:
        session.get(FundAccount, 1).balance_vnd += 1
    result = collect(database, journal)
    assert result["fund_balanced"] is False
