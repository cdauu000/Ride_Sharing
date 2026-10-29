const fs = require("node:fs");
const path = require("node:path");

async function main() {
  const { network: networkManager } = await import("hardhat");
  const { ethers } = await networkManager.create();
  const network = await ethers.provider.getNetwork();
  if (network.chainId !== 31337n) throw new Error("This script is restricted to local chain 31337; external deployment needs separate configuration.");
  const [operator, treasury] = await ethers.getSigners();
  const Token = await ethers.getContractFactory("TestVND");
  const token = await Token.deploy(operator.address); await token.waitForDeployment();
  const Escrow = await ethers.getContractFactory("RideEscrow");
  const escrow = await Escrow.deploy(await token.getAddress(), operator.address, operator.address, treasury.address);
  await escrow.waitForDeployment();
  await (await token.mint(operator.address, 5000000n)).wait();
  await (await token.approve(await escrow.getAddress(), 5000000n)).wait();
  await (await escrow.seedFund(5000000n)).wait();
  const deployment = { network: "localhost", chain_id: Number(network.chainId), token: await token.getAddress(),
    escrow: await escrow.getAddress(), operator: operator.address, treasury: treasury.address, mode: "LOCAL_EVM_TEST_CREDITS" };
  fs.mkdirSync(path.resolve(__dirname, "../deployments"), { recursive: true });
  fs.writeFileSync(path.resolve(__dirname, "../deployments/localhost.json"), JSON.stringify(deployment, null, 2) + "\n");
  console.log(deployment);
}
main().catch(error => { console.error(error); process.exitCode = 1; });
