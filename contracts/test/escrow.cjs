const { expect } = require("chai");
let ethers, provider;

describe("Revision 9 integer-VND escrow", function () {
  let token, escrow, admin, treasury, passenger, driver, stranger, passengerB;
  const id = text => ethers.id(text);
  before(async function () {
    const { network } = await import("hardhat");
    const connection = await network.create();
    ethers = connection.ethers;
    provider = connection.provider;
  });
  async function fails(promise, message) {
    try { await (await promise).wait(); } catch (error) {
      if (message) expect(String(error)).to.include(message);
      return;
    }
    throw new Error("Expected transaction rejection");
  }
  async function send(promise) { return (await promise).wait(); }
  async function pool(name = "pool", who = passenger, amount = 174000n, quote = 155000n, target = 155200n) {
    await send(escrow.createAndDepositPoolCap(id(name), id("plan"), who.address, driver.address, amount, quote, target));
    return id(name);
  }
  async function finish(bookingId) {
    await send(escrow.markRideStarted(bookingId));
    await send(escrow.markRideCompleted(bookingId));
    await send(escrow.releasePayment(bookingId));
  }
  async function conserved() {
    expect(await token.balanceOf(await escrow.getAddress())).to.equal(await escrow.guaranteeFundBalance() + await escrow.totalBookingLiability());
  }
  beforeEach(async function () {
    [admin, treasury, passenger, driver, stranger, passengerB] = await ethers.getSigners();
    token = await (await ethers.getContractFactory("TestVND")).deploy(admin.address);
    escrow = await (await ethers.getContractFactory("RideEscrow")).deploy(await token.getAddress(), admin.address, admin.address, treasury.address);
    await token.waitForDeployment(); await escrow.waitForDeployment();
    for (const who of [admin, passenger, passengerB]) {
      await send(token.mint(who.address, 10000000n));
      await send(token.connect(who).approve(await escrow.getAddress(), 10000000n));
    }
    await send(escrow.seedFund(5000000n));
  });

  it("uses indivisible research credits and owner-only issuance", async function () {
    expect(await token.decimals()).to.equal(0n);
    await fails(token.connect(stranger).mint(stranger.address, 1000n));
  });
  it("restricts deposits, completion, fund seed and arbitration by role", async function () {
    await fails(escrow.connect(stranger).createAndDepositFixed(id("x"), id("p"), passenger.address, driver.address, 0, 81000n));
    await fails(escrow.connect(stranger).seedFund(1000n));
    await fails(escrow.connect(stranger).markRideCompleted(id("x")));
    await fails(escrow.connect(stranger).resolveDispute(id("x"), 0, 0, 0));
  });
  it("bike regression: 81000 = 64800 + 16200", async function () {
    await send(escrow.createAndDepositFixed(id("bike"), id("p"), passenger.address, driver.address, 0, 81000n));
    await finish(id("bike"));
    const b = await escrow.getBooking(id("bike"));
    expect(b.driverPaidVnd).to.equal(64800n); expect(b.platformPaidVnd).to.equal(16200n);
    await conserved();
  });
  it("intercity private regression: 637000 -> 541450 driver", async function () {
    await send(escrow.createAndDepositFixed(id("private"), id("p"), passenger.address, driver.address, 3, 637000n));
    await finish(id("private"));
    expect((await escrow.getBooking(id("private"))).driverPaidVnd).to.equal(541450n);
    await conserved();
  });
  it("pool A+B refunds caps and splits 248000 exactly", async function () {
    const a = await pool("a");
    const b = await pool("b", passengerB, 119000n, 106000n, 106400n);
    await send(escrow.lockFinalPriceAndRefundDiff(a, 143000n, true, false));
    await send(escrow.lockFinalPriceAndRefundDiff(b, 105000n, true, false));
    await finish(a); await finish(b);
    const ba = await escrow.getBooking(a), bb = await escrow.getBooking(b);
    expect(ba.refundedVnd).to.equal(31000n); expect(bb.refundedVnd).to.equal(14000n);
    expect(ba.driverPaidVnd + bb.driverPaidVnd).to.equal(210800n);
    expect(ba.platformPaidVnd + bb.platformPaidVnd).to.equal(29760n);
    expect(await escrow.guaranteeFundBalance()).to.equal(5007440n);
    await conserved();
  });
  it("unmatched market guarantee pays exactly 7300", async function () {
    const a = await pool();
    await send(escrow.lockFinalPriceAndRefundDiff(a, 174000n, false, false));
    await finish(a);
    const b = await escrow.getBooking(a);
    expect(b.guaranteeVnd).to.equal(7300n); expect(b.driverPaidVnd).to.equal(155200n);
    expect(b.platformPaidVnd).to.equal(26100n); expect(await escrow.guaranteeFundBalance()).to.equal(4992700n);
    await conserved();
  });
  it("driver breaking pooling loses guarantee and passenger pays only quote", async function () {
    const a = await pool();
    await send(escrow.lockFinalPriceAndRefundDiff(a, 155000n, false, true));
    await finish(a);
    const b = await escrow.getBooking(a);
    expect(b.refundedVnd).to.equal(19000n); expect(b.driverPaidVnd).to.equal(131750n); expect(b.guaranteeVnd).to.equal(0n);
    await conserved();
  });
  it("preserves locked price and funds late corider cancellation shortfall", async function () {
    const a = await pool();
    await send(escrow.lockFinalPriceAndRefundDiff(a, 143000n, true, false));
    await send(escrow.protectLateCancellation(a, 15500n));
    await finish(a);
    const b = await escrow.getBooking(a);
    expect(b.finalVnd).to.equal(143000n); expect(b.guaranteeVnd).to.equal(18150n);
    expect(b.driverPaidVnd + 15500n).to.equal(155200n);
    await conserved();
  });
  it("prevents duplicated booking, lock, completion and release", async function () {
    const a = await pool();
    await fails(escrow.createAndDepositPoolCap(a, id("p"), passenger.address, driver.address, 174000n, 155000n, 155200n), "DuplicateBooking");
    await send(escrow.lockFinalPriceAndRefundDiff(a, 143000n, true, false));
    await fails(escrow.lockFinalPriceAndRefundDiff(a, 140000n, true, false), "InvalidState");
    await finish(a);
    await fails(escrow.releasePayment(a), "InvalidState");
    await fails(escrow.markRideCompleted(a), "InvalidState");
    await conserved();
  });
  it("rejects wrong service, non-granular fares and invalid caps", async function () {
    await fails(escrow.createAndDepositFixed(id("x"), id("p"), passenger.address, driver.address, 2, 81000n), "InvalidService");
    await fails(escrow.createAndDepositFixed(id("x"), id("p"), passenger.address, driver.address, 0, 81001n), "InvalidAmount");
    await fails(escrow.createAndDepositPoolCap(id("p"), id("t"), passenger.address, driver.address, 174000n, 175000n, 155200n), "InvalidAmount");
    const a = await pool();
    await fails(escrow.lockFinalPriceAndRefundDiff(a, 156000n, true, false), "InvalidAmount");
    await fails(escrow.lockFinalPriceAndRefundDiff(a, 174000n, false, true), "InvalidAmount");
    await fails(escrow.lockFinalPriceAndRefundDiff(a, 155000n, false, false), "InvalidAmount");
    await conserved();
  });
  it("blocks completion without start or price lock and premature release", async function () {
    const a = await pool();
    await fails(escrow.markRideCompleted(a), "InvalidState");
    await fails(escrow.releasePayment(a), "InvalidState");
    await send(escrow.markRideStarted(a));
    await fails(escrow.markRideCompleted(a), "InvalidState");
    await send(escrow.lockFinalPriceAndRefundDiff(a, 143000n, true, false));
    await send(escrow.markRideCompleted(a));
    await fails(escrow.autoRelease(a), "AutoReleaseTooEarly");
    await provider.request({ method: "evm_increaseTime", params: [86400] });
    await provider.request({ method: "evm_mine", params: [] });
    await send(escrow.connect(stranger).autoRelease(a));
    await conserved();
  });
  it("topup uses 15% commission and needs no passenger fare increase elsewhere", async function () {
    const a = id("seat");
    await send(escrow.createAndDepositIntercityPool(a, id("trip"), passenger.address, driver.address, 200000n));
    await send(escrow.topUpEscrow(a, 118000n));
    await fails(escrow.topUpEscrow(a, 1000n), "InvalidState");
    await finish(a);
    const b = await escrow.getBooking(a);
    expect(b.finalVnd).to.equal(318000n); expect(b.driverPaidVnd).to.equal(270300n); expect(b.platformPaidVnd).to.equal(47700n);
    await conserved();
  });
  it("normal intercity seats use 10% commission", async function () {
    await send(escrow.createAndDepositIntercityPool(id("seat"), id("trip"), passenger.address, driver.address, 600000n));
    await finish(id("seat"));
    expect((await escrow.getBooking(id("seat"))).driverPaidVnd).to.equal(540000n);
    await conserved();
  });
  it("compensates a partial topup batch and restores the 10% seat mode", async function () {
    const a = id("seat");
    await send(escrow.createAndDepositIntercityPool(a, id("trip"), passenger.address, driver.address, 200000n));
    await send(escrow.topUpEscrow(a, 118000n));
    await send(escrow.revertTopUpEscrow(a));
    await finish(a);
    const b = await escrow.getBooking(a);
    expect(b.finalVnd).to.equal(200000n); expect(b.refundedVnd).to.equal(118000n);
    expect(b.driverPaidVnd).to.equal(180000n); expect(b.topupMode).to.equal(false);
    await conserved();
  });
  it("merge only reduces price and switches the receiving driver", async function () {
    const a = id("seat");
    await send(escrow.createAndDepositIntercityPool(a, id("trip"), passenger.address, driver.address, 220000n));
    await fails(escrow.reassignIntercityBooking(a, id("trip2"), stranger.address, 230000n), "InvalidAmount");
    await send(escrow.reassignIntercityBooking(a, id("trip2"), stranger.address, 200000n));
    const b = await escrow.getBooking(a);
    expect(b.driver).to.equal(stranger.address); expect(b.refundedVnd).to.equal(20000n);
    await finish(a); await conserved();
  });
  it("free cancellation refunds 100% and forbids release", async function () {
    const a = await pool();
    await send(escrow.cancelAndRefund(a, 0, 0, 0, 0));
    expect((await escrow.getBooking(a)).refundedVnd).to.equal(174000n);
    await fails(escrow.releasePayment(a), "InvalidState"); await conserved();
  });
  it("late pool cancellation deposits penalty into guarantee fund", async function () {
    const a = await pool();
    await fails(escrow.cancelAndRefund(a, 31000n, 15500n, 15000n, 0), "InvalidAmount");
    await send(escrow.cancelAndRefund(a, 31000n, 15500n, 15500n, 0));
    const b = await escrow.getBooking(a);
    expect(b.refundedVnd).to.equal(143000n); expect(b.driverPaidVnd).to.equal(15500n);
    expect(await escrow.guaranteeFundBalance()).to.equal(5015500n);
    await conserved();
  });
  it("dispute freezes release and requires exact arbiter split", async function () {
    const a = await pool();
    await fails(escrow.connect(stranger).raiseDispute(a), "NotParticipant");
    await send(escrow.connect(passenger).raiseDispute(a));
    await fails(escrow.cancelAndRefund(a, 0, 0, 0, 0), "InvalidState");
    await fails(escrow.resolveDispute(a, 100000n, 70000n, 0), "InvalidAmount");
    await send(escrow.resolveDispute(a, 100000n, 70000n, 4000n));
    expect((await escrow.getBooking(a)).state).to.equal(7n);
    await conserved();
  });
  it("insufficient guarantee fund reverts every payout atomically", async function () {
    const tinyEscrow = await (await ethers.getContractFactory("RideEscrow")).deploy(await token.getAddress(), admin.address, admin.address, treasury.address);
    await send(token.connect(passenger).approve(await tinyEscrow.getAddress(), 174000n));
    await send(tinyEscrow.createAndDepositPoolCap(id("a"), id("p"), passenger.address, driver.address, 174000n, 155000n, 155200n));
    await send(tinyEscrow.lockFinalPriceAndRefundDiff(id("a"), 174000n, false, false));
    await send(tinyEscrow.markRideStarted(id("a"))); await send(tinyEscrow.markRideCompleted(id("a")));
    await fails(tinyEscrow.releasePayment(id("a")), "FundInsufficient");
    expect((await tinyEscrow.getBooking(id("a"))).balanceVnd).to.equal(174000n);
    expect(await token.balanceOf(driver.address)).to.equal(0n);
  });
});
