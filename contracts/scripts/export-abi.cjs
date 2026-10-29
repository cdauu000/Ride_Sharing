const fs = require("node:fs");
const path = require("node:path");
const dir = path.resolve(__dirname, "../abi");
fs.mkdirSync(dir, { recursive: true });
for (const name of ["RideEscrow", "TestVND"]) {
  const source = JSON.parse(fs.readFileSync(path.resolve(__dirname, `../artifacts/src/${name}.sol/${name}.json`), "utf8"));
  fs.writeFileSync(path.join(dir, `${name}.json`), JSON.stringify(source.abi, null, 2) + "\n");
}
