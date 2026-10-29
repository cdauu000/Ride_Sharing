"""Run Python relayer against an ephemeral local EVM, using generated test keys.

Run from repository root: .venv/Scripts/python.exe contracts/scripts/verify_adapter.py
This does not deploy externally or read production/testnet credentials.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eth_account import Account  # noqa: E402
from web3 import Web3  # noqa: E402

from app.escrow import EscrowCommand  # noqa: E402
from app.escrow.evm import CustodialWallets, EvmSettings, Web3EscrowAdapter  # noqa: E402


def main() -> None:
    Account.enable_unaudited_hdwallet_features()
    _, mnemonic = Account.create_with_mnemonic()
    child_env = {**os.environ, "LOCAL_EVM_MNEMONIC": mnemonic}
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    rpc = f"http://127.0.0.1:{port}"
    child_env["LOCAL_EVM_RPC"] = rpc
    workdir = ROOT / "contracts"
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with tempfile.TemporaryDirectory(prefix="ride-evm-") as temp:
        scratch = Path(temp)
        # Hardhat's standard cache/config stays in this disposable verification dir.
        child_env["APPDATA"] = str(scratch / "config")
        child_env["LOCALAPPDATA"] = str(scratch / "cache")
        cli = str(workdir / "node_modules/hardhat/dist/src/cli.js")
        with (scratch / "node.log").open("w", encoding="utf8") as log:
            process = subprocess.Popen(["node", cli, "node", "--network", "hardhatMainnet", "--hostname", "127.0.0.1", "--port", str(port)], cwd=workdir,
                                       env=child_env, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            try:
                web3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 2}))
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if web3.is_connected():
                        break
                    if process.poll() is not None:
                        raise RuntimeError("Local EVM exited before becoming ready")
                    time.sleep(0.25)
                else:
                    raise RuntimeError("Local EVM did not start")
                subprocess.run(["node", cli, "run", "scripts/deploy.cjs", "--network", "localhost"], cwd=workdir,
                               env=child_env, check=True, capture_output=True, text=True, timeout=90, creationflags=flags)
                deployment = json.loads((workdir / "deployments/localhost.json").read_text())
                operator = Account.from_mnemonic(mnemonic, account_path="m/44'/60'/0'/0/0")
                passenger = Account.from_mnemonic(mnemonic, account_path="m/44'/60'/0'/0/2")
                driver = Account.from_mnemonic(mnemonic, account_path="m/44'/60'/0'/0/3")
                token = web3.eth.contract(address=deployment["token"], abi=json.loads((workdir / "abi/TestVND.json").read_text()))

                def send(function: object, signer: object) -> None:
                    transaction = function.build_transaction({"from": signer.address, "nonce": web3.eth.get_transaction_count(signer.address), "chainId": 31337})
                    signed = signer.sign_transaction(transaction)
                    receipt = web3.eth.wait_for_transaction_receipt(web3.eth.send_raw_transaction(signed.raw_transaction))
                    if receipt["status"] != 1:
                        raise RuntimeError("Local setup transaction failed")

                send(token.functions.mint(passenger.address, 1_000_000), operator)
                send(token.functions.approve(deployment["escrow"], 1_000_000), passenger)
                key_env = "RIDE_EPHEMERAL_TEST_RELAYER_KEY"
                mnemonic_env = "RIDE_EPHEMERAL_TEST_MNEMONIC"
                os.environ[key_env] = operator.key.hex()
                os.environ[mnemonic_env] = mnemonic
                try:
                    settings = EvmSettings(rpc, 31337, deployment["escrow"], workdir / "abi/RideEscrow.json", scratch / "journal.sqlite", private_key_env=key_env, receipt_timeout_s=5)
                    adapter = Web3EscrowAdapter(settings)
                    wallet = CustodialWallets(scratch / "wallets.sqlite", mnemonic_env)
                    assert wallet.address("user-a") == wallet.address("user-a")
                    assert wallet.address("user-a") != wallet.address("user-b")
                    commands = [
                        EscrowCommand("deposit-a", "DEPOSIT_POOL", "booking-a", {"passenger": passenger.address, "driver": driver.address, "amount_vnd": 174000, "service_code": "CAR_URBAN_POOL", "quote_vnd": 155000, "target_driver_vnd": 155200, "trip_id": "plan-a"}),
                        EscrowCommand("lock-a", "LOCK", "booking-a", {"final_vnd": 174000}),
                        EscrowCommand("start-a", "START", "booking-a"),
                        EscrowCommand("complete-a", "COMPLETE", "booking-a"),
                        EscrowCommand("release-a", "RELEASE", "booking-a"),
                    ]
                    for command in commands:
                        receipt = adapter.execute(command)
                        assert receipt.status == "CONFIRMED", receipt
                        assert receipt.mode == "LOCAL_EVM"
                        assert receipt.tx_hash and receipt.tx_hash.startswith("0x")
                        repeated = adapter.execute(command)
                        assert repeated.tx_hash == receipt.tx_hash
                        # Simulate process death after chain receipt but before
                        # the journal's confirmation commit, then recover.
                        with closing(sqlite3.connect(settings.journal_path)) as journal:
                            with journal:
                                journal.execute("UPDATE evm_operations SET status='SUBMITTED' WHERE operation_id=?", (command.operation_id,))
                        recovered = Web3EscrowAdapter(settings).execute(command)
                        assert recovered.tx_hash == receipt.tx_hash
                        assert recovered.status == "CONFIRMED"
                    result = adapter.get("booking-a")
                    assert result["driver_paid_vnd"] == 155200
                    assert result["guarantee_vnd"] == 7300
                    assert result["fund_balance_vnd"] == 4_992_700
                    assert Web3EscrowAdapter(settings).get("booking-a") == result
                    assert token.functions.balanceOf(driver.address).call() == 155200
                    print(json.dumps({"mode": "LOCAL_EVM", "verified_operations": len(commands), "retries": "same transaction hash", "driver_vnd": 155200, "guarantee_vnd": 7300, "fund_vnd": 4992700, "external_deployment": False}))
                finally:
                    os.environ.pop(key_env, None)
                    os.environ.pop(mnemonic_env, None)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
