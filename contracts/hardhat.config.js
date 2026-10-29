import { createRequire } from "node:module";
import { defineConfig } from "hardhat/config";
import hardhatEthers from "@nomicfoundation/hardhat-ethers";
import hardhatMocha from "@nomicfoundation/hardhat-mocha";

const require = createRequire(import.meta.url);
export default defineConfig({
  plugins: [hardhatEthers, hardhatMocha],
  solidity: {
    version: "0.8.38",
    path: require.resolve("solc/soljson.js"),
    preferWasm: true,
    settings: { optimizer: { enabled: true, runs: 200 }, viaIR: true, evmVersion: "cancun" },
  },
  networks: {
    hardhatMainnet: {
      type: "edr-simulated", chainType: "l1", chainId: 31337,
      ...(process.env.LOCAL_EVM_MNEMONIC ? { accounts: { mnemonic: process.env.LOCAL_EVM_MNEMONIC } } : {}),
    },
    localhost: { type: "http", chainType: "l1", url: process.env.LOCAL_EVM_RPC || "http://127.0.0.1:8545" },
  },
  paths: { sources: "./src", tests: { mocha: "./test" }, cache: "./cache", artifacts: "./artifacts" },
  test: { mocha: { timeout: 60000 } },
});
