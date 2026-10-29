// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @notice Per-booking escrow for test credits, implementing Revision 9 D-33..D-52.
/// @dev The authorized application attests physical ride events; the chain enforces
/// money, one-way lifecycle gates, roles and conservation. This is not a bank.
contract RideEscrow is AccessControl, ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 public constant RELAYER_ROLE = keccak256("RELAYER_ROLE");
    bytes32 public constant ARBITER_ROLE = keccak256("ARBITER_ROLE");
    uint256 public constant AUTO_RELEASE_DELAY = 24 hours;

    enum Service { BIKE_URBAN, CAR_URBAN_PRIVATE, CAR_URBAN_POOL, CAR_INTERCITY_PRIVATE, CAR_INTERCITY_POOL }
    enum State { NONE, DEPOSITED, LOCKED, TOPPED_UP, RELEASED, REFUNDED, DISPUTED, RESOLVED }

    struct Booking {
        address passenger;
        address driver;
        bytes32 tripId;
        Service service;
        State state;
        uint256 capVnd;
        uint256 balanceVnd;
        uint256 quoteVnd;
        uint256 targetDriverVnd;
        uint256 finalVnd;
        uint256 refundedVnd;
        uint256 driverPaidVnd;
        uint256 platformPaidVnd;
        uint256 fundContributionVnd;
        uint256 guaranteeVnd;
        uint256 completedAt;
        bool priceLocked;
        bool matched;
        bool driverDeclined;
        bool started;
        bool completed;
        bool topupMode;
        bool lateCancellationProtection;
        uint256 creditedCancellationVnd;
        uint256 topupOriginalVnd;
    }

    IERC20 public immutable token;
    address public immutable platform;
    uint256 public guaranteeFundBalance;
    uint256 public totalBookingLiability;
    mapping(bytes32 => Booking) private bookings;

    error InvalidAmount();
    error InvalidState();
    error DuplicateBooking();
    error InvalidAddress();
    error InvalidService();
    error FundInsufficient();
    error NotParticipant();
    error AutoReleaseTooEarly();

    event EscrowDeposited(bytes32 indexed bookingId, bytes32 indexed tripId, address indexed passenger, uint256 amountVnd);
    event PriceLocked(bytes32 indexed bookingId, uint256 finalVnd, uint256 refundVnd, bool matched, bool driverDeclined);
    event EscrowToppedUp(bytes32 indexed bookingId, uint256 amountVnd, uint256 newFinalVnd);
    event TopupReverted(bytes32 indexed bookingId, uint256 refundVnd, uint256 restoredFinalVnd);
    event BookingReassigned(bytes32 indexed bookingId, bytes32 indexed tripId, address indexed driver);
    event RideStarted(bytes32 indexed bookingId);
    event RideCompleted(bytes32 indexed bookingId, uint256 completedAt);
    event PaymentReleased(bytes32 indexed bookingId, uint256 driverVnd, uint256 platformVnd, uint256 fundVnd, uint256 guaranteeVnd);
    event EscrowRefunded(bytes32 indexed bookingId, uint256 refundVnd, uint256 feeVnd);
    event FundSeeded(uint256 amountVnd, uint256 balanceVnd);
    event FundContributionRecorded(bytes32 indexed bookingId, uint256 amountVnd, uint256 balanceVnd);
    event GuaranteePayoutRecorded(bytes32 indexed bookingId, address indexed driver, uint256 amountVnd, uint256 balanceVnd);
    event DisputeRaised(bytes32 indexed bookingId);
    event DisputeResolved(bytes32 indexed bookingId, uint256 passengerVnd, uint256 driverVnd, uint256 platformVnd);

    constructor(IERC20 testToken, address admin, address relayer, address treasury) {
        if (address(testToken) == address(0) || admin == address(0) || relayer == address(0) || treasury == address(0)) revert InvalidAddress();
        token = testToken;
        platform = treasury;
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ARBITER_ROLE, admin);
        _grantRole(RELAYER_ROLE, relayer);
    }

    function getBooking(bytes32 bookingId) external view returns (Booking memory) { return bookings[bookingId]; }

    function seedFund(uint256 amountVnd) external onlyRole(DEFAULT_ADMIN_ROLE) nonReentrant {
        if (amountVnd == 0) revert InvalidAmount();
        guaranteeFundBalance += amountVnd;
        token.safeTransferFrom(msg.sender, address(this), amountVnd);
        emit FundSeeded(amountVnd, guaranteeFundBalance);
    }

    function createAndDepositFixed(bytes32 bookingId, bytes32 tripId, address passenger, address driver, Service service, uint256 amountVnd)
        external onlyRole(RELAYER_ROLE) nonReentrant
    {
        if (service != Service.BIKE_URBAN && service != Service.CAR_URBAN_PRIVATE && service != Service.CAR_INTERCITY_PRIVATE) revert InvalidService();
        _create(bookingId, tripId, passenger, driver, service, amountVnd);
        Booking storage b = bookings[bookingId];
        b.finalVnd = amountVnd;
        b.priceLocked = true;
    }

    function createAndDepositPoolCap(bytes32 bookingId, bytes32 tripId, address passenger, address driver, uint256 capVnd, uint256 quoteVnd, uint256 targetDriverVnd)
        external onlyRole(RELAYER_ROLE) nonReentrant
    {
        _fare(quoteVnd);
        if (quoteVnd >= capVnd || targetDriverVnd == 0 || targetDriverVnd > capVnd) revert InvalidAmount();
        _create(bookingId, tripId, passenger, driver, Service.CAR_URBAN_POOL, capVnd);
        Booking storage b = bookings[bookingId];
        b.quoteVnd = quoteVnd;
        b.targetDriverVnd = targetDriverVnd;
    }

    function createAndDepositIntercityPool(bytes32 bookingId, bytes32 tripId, address passenger, address driver, uint256 amountVnd)
        external onlyRole(RELAYER_ROLE) nonReentrant
    {
        _create(bookingId, tripId, passenger, driver, Service.CAR_INTERCITY_POOL, amountVnd);
        Booking storage b = bookings[bookingId];
        b.finalVnd = amountVnd;
        b.priceLocked = true;
    }

    function _create(bytes32 id, bytes32 tripId, address passenger, address driver, Service service, uint256 amountVnd) private {
        if (id == bytes32(0) || bookings[id].state != State.NONE) revert DuplicateBooking();
        if (passenger == address(0) || driver == address(0) || passenger == driver) revert InvalidAddress();
        _fare(amountVnd);
        Booking storage b = bookings[id];
        b.passenger = passenger; b.driver = driver; b.tripId = tripId; b.service = service;
        b.state = State.DEPOSITED; b.capVnd = amountVnd; b.balanceVnd = amountVnd;
        totalBookingLiability += amountVnd;
        token.safeTransferFrom(passenger, address(this), amountVnd);
        emit EscrowDeposited(id, tripId, passenger, amountVnd);
    }

    function lockFinalPriceAndRefundDiff(bytes32 id, uint256 finalVnd, bool matched, bool driverDeclined)
        external onlyRole(RELAYER_ROLE) nonReentrant
    {
        Booking storage b = bookings[id];
        _active(b);
        if (b.priceLocked || b.service != Service.CAR_URBAN_POOL) revert InvalidState();
        _fare(finalVnd);
        if (finalVnd > b.balanceVnd || (matched && (driverDeclined || finalVnd > b.quoteVnd))) revert InvalidAmount();
        if (driverDeclined && finalVnd != b.quoteVnd) revert InvalidAmount();
        if (!matched && !driverDeclined && finalVnd != b.capVnd) revert InvalidAmount();
        b.matched = matched; b.driverDeclined = driverDeclined; b.priceLocked = true;
        b.finalVnd = finalVnd; b.state = State.LOCKED;
        uint256 refundVnd = _reduce(b, finalVnd);
        emit PriceLocked(id, finalVnd, refundVnd, matched, driverDeclined);
    }

    function topUpEscrow(bytes32 id, uint256 amountVnd) external onlyRole(RELAYER_ROLE) nonReentrant {
        Booking storage b = bookings[id];
        _active(b);
        _fare(amountVnd);
        if (b.service != Service.CAR_INTERCITY_POOL || b.started || b.topupMode) revert InvalidState();
        // Passenger consent and its immutable API idempotency record precede this call.
        b.topupOriginalVnd = b.finalVnd;
        b.topupMode = true; b.balanceVnd += amountVnd; b.finalVnd += amountVnd; b.state = State.TOPPED_UP;
        totalBookingLiability += amountVnd;
        token.safeTransferFrom(b.passenger, address(this), amountVnd);
        emit EscrowToppedUp(id, amountVnd, b.finalVnd);
    }

    /// @notice Compensation when another passenger's accepted topup fails funding.
    /// Restores the original seat fare and 10% commission before an under-min run.
    function revertTopUpEscrow(bytes32 id) external onlyRole(RELAYER_ROLE) nonReentrant {
        Booking storage b = bookings[id]; _active(b);
        if (b.service != Service.CAR_INTERCITY_POOL || !b.topupMode || b.started) revert InvalidState();
        b.topupMode = false; b.finalVnd = b.topupOriginalVnd; b.state = State.LOCKED;
        uint256 refund = _reduce(b, b.finalVnd);
        b.topupOriginalVnd = 0;
        emit TopupReverted(id, refund, b.finalVnd);
    }

    function reassignIntercityBooking(bytes32 id, bytes32 tripId, address driver, uint256 newFinalVnd)
        external onlyRole(RELAYER_ROLE) nonReentrant
    {
        Booking storage b = bookings[id];
        _active(b); _fare(newFinalVnd);
        if (b.service != Service.CAR_INTERCITY_POOL || b.started || b.topupMode) revert InvalidState();
        if (driver == address(0) || driver == b.passenger) revert InvalidAddress();
        if (newFinalVnd > b.balanceVnd) revert InvalidAmount();
        b.tripId = tripId; b.driver = driver; b.finalVnd = newFinalVnd; b.state = State.LOCKED;
        uint256 refund = _reduce(b, newFinalVnd);
        emit BookingReassigned(id, tripId, driver);
        emit PriceLocked(id, newFinalVnd, refund, false, false);
    }

    function markRideStarted(bytes32 id) external onlyRole(RELAYER_ROLE) {
        Booking storage b = bookings[id]; _active(b);
        if (b.started) revert InvalidState();
        b.started = true; emit RideStarted(id);
    }

    function markRideCompleted(bytes32 id) external onlyRole(RELAYER_ROLE) {
        Booking storage b = bookings[id]; _active(b);
        if (!b.started || !b.priceLocked || b.completed) revert InvalidState();
        b.completed = true; b.completedAt = block.timestamp;
        emit RideCompleted(id, block.timestamp);
    }

    /// @notice Preserve the frozen passenger fare when a corider cancels late.
    /// Credited penalty is the part already paid to this plan's driver.
    function protectLateCancellation(bytes32 id, uint256 creditedPenaltyVnd) external onlyRole(RELAYER_ROLE) {
        Booking storage b = bookings[id]; _active(b);
        if (b.service != Service.CAR_URBAN_POOL || !b.priceLocked || !b.matched || b.completed) revert InvalidState();
        if (creditedPenaltyVnd < b.creditedCancellationVnd) revert InvalidAmount();
        b.lateCancellationProtection = true;
        b.creditedCancellationVnd = creditedPenaltyVnd;
    }

    function releasePayment(bytes32 id) external onlyRole(RELAYER_ROLE) nonReentrant { _release(id); }

    function autoRelease(bytes32 id) external nonReentrant {
        Booking storage b = bookings[id];
        if (!b.completed || block.timestamp < b.completedAt + AUTO_RELEASE_DELAY) revert AutoReleaseTooEarly();
        _release(id);
    }

    function _release(bytes32 id) private {
        Booking storage b = bookings[id]; _active(b);
        if (!b.completed || !b.priceLocked) revert InvalidState();
        uint256 fare = b.balanceVnd;
        uint256 driverVnd; uint256 platformVnd; uint256 contribution; uint256 guarantee;
        if (b.service == Service.CAR_URBAN_POOL) {
            driverVnd = fare * 85 / 100;
            if (b.matched) { contribution = fare * 3 / 100; platformVnd = fare - driverVnd - contribution; }
            else { platformVnd = fare - driverVnd; }
            bool eligible = (!b.matched && !b.driverDeclined) || b.lateCancellationProtection;
            uint256 credited = b.lateCancellationProtection ? b.creditedCancellationVnd : 0;
            if (eligible && b.targetDriverVnd > driverVnd + credited) guarantee = b.targetDriverVnd - driverVnd - credited;
        } else {
            uint256 rate = (b.service == Service.BIKE_URBAN || b.service == Service.CAR_URBAN_PRIVATE) ? 20 : 15;
            if (b.service == Service.CAR_INTERCITY_POOL && !b.topupMode) rate = 10;
            platformVnd = fare * rate / 100; driverVnd = fare - platformVnd;
        }
        if (guarantee > guaranteeFundBalance + contribution) revert FundInsufficient();
        b.state = State.RELEASED; b.balanceVnd = 0;
        b.driverPaidVnd = driverVnd + guarantee; b.platformPaidVnd = platformVnd;
        b.fundContributionVnd = contribution; b.guaranteeVnd = guarantee;
        totalBookingLiability -= fare;
        guaranteeFundBalance += contribution;
        if (contribution > 0) emit FundContributionRecorded(id, contribution, guaranteeFundBalance);
        guaranteeFundBalance -= guarantee;
        if (guarantee > 0) emit GuaranteePayoutRecorded(id, b.driver, guarantee, guaranteeFundBalance);
        token.safeTransfer(b.driver, driverVnd + guarantee);
        token.safeTransfer(platform, platformVnd);
        emit PaymentReleased(id, driverVnd + guarantee, platformVnd, contribution, guarantee);
    }

    function cancelAndRefund(bytes32 id, uint256 feeVnd, uint256 toFundVnd, uint256 toDriverVnd, uint256 toPlatformVnd)
        external onlyRole(RELAYER_ROLE) nonReentrant
    {
        Booking storage b = bookings[id]; _active(b);
        if (b.completed || feeVnd > b.balanceVnd || feeVnd != toFundVnd + toDriverVnd + toPlatformVnd) revert InvalidAmount();
        uint256 balance = b.balanceVnd; uint256 refund = balance - feeVnd;
        b.state = State.REFUNDED; b.balanceVnd = 0; b.refundedVnd += refund;
        b.driverPaidVnd = toDriverVnd; b.platformPaidVnd = toPlatformVnd; b.fundContributionVnd = toFundVnd;
        totalBookingLiability -= balance; guaranteeFundBalance += toFundVnd;
        if (toFundVnd > 0) emit FundContributionRecorded(id, toFundVnd, guaranteeFundBalance);
        if (refund > 0) token.safeTransfer(b.passenger, refund);
        if (toDriverVnd > 0) token.safeTransfer(b.driver, toDriverVnd);
        if (toPlatformVnd > 0) token.safeTransfer(platform, toPlatformVnd);
        emit EscrowRefunded(id, refund, feeVnd);
    }

    function raiseDispute(bytes32 id) external {
        Booking storage b = bookings[id]; _active(b);
        if (msg.sender != b.passenger && msg.sender != b.driver && !hasRole(RELAYER_ROLE, msg.sender)) revert NotParticipant();
        b.state = State.DISPUTED; emit DisputeRaised(id);
    }

    function resolveDispute(bytes32 id, uint256 passengerVnd, uint256 driverVnd, uint256 platformVnd)
        external onlyRole(ARBITER_ROLE) nonReentrant
    {
        Booking storage b = bookings[id];
        if (b.state != State.DISPUTED) revert InvalidState();
        if (passengerVnd + driverVnd + platformVnd != b.balanceVnd) revert InvalidAmount();
        totalBookingLiability -= b.balanceVnd; b.balanceVnd = 0; b.state = State.RESOLVED;
        b.refundedVnd += passengerVnd; b.driverPaidVnd = driverVnd; b.platformPaidVnd = platformVnd;
        if (passengerVnd > 0) token.safeTransfer(b.passenger, passengerVnd);
        if (driverVnd > 0) token.safeTransfer(b.driver, driverVnd);
        if (platformVnd > 0) token.safeTransfer(platform, platformVnd);
        emit DisputeResolved(id, passengerVnd, driverVnd, platformVnd);
    }

    function _reduce(Booking storage b, uint256 finalVnd) private returns (uint256 refund) {
        refund = b.balanceVnd - finalVnd;
        b.balanceVnd = finalVnd; b.refundedVnd += refund; totalBookingLiability -= refund;
        if (refund > 0) token.safeTransfer(b.passenger, refund);
    }

    function _active(Booking storage b) private view {
        if (b.state != State.DEPOSITED && b.state != State.LOCKED && b.state != State.TOPPED_UP) revert InvalidState();
    }

    function _fare(uint256 amount) private pure { if (amount == 0 || amount % 1000 != 0) revert InvalidAmount(); }
}
