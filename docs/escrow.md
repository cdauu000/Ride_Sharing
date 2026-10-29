# Ký quỹ Revision 9: giao thức, kiểm thử và vận hành

Đơn vị cơ sở là **1 VND nguyên**. `TestVND` có `decimals() = 0`, là tín dụng nghiên cứu không có bảo chứng hoặc khả năng đổi tiền thật. `RideEscrow` giữ cả tiền ký quỹ theo booking và Quỹ bảo đảm; không dùng chuyển tiền giữa hai ví để mô phỏng việc chi Quỹ.

## Thành phần đã xây dựng

| Thành phần | Nơi thực hiện | Trách nhiệm |
|---|---|---|
| Token tín dụng thử nghiệm | `contracts/src/TestVND.sol` | Chỉ operator được phát hành; 1 đơn vị = 1 VND |
| Hợp đồng ký quỹ | `contracts/src/RideEscrow.sol` | Mỗi `bytes32 bookingId` có đúng một bản ghi; ký quỹ, hoàn chênh lệch, góp thêm, gộp, giải ngân và phân xử |
| Adapter mô phỏng bền vững | `app/escrow/local.py` | SQLite journal, transaction nguyên tử, chống thực thi trùng, tiền nguyên; luôn ghi `LOCAL_SIMULATION`, `tx_hash = null` |
| Adapter EVM | `app/escrow/evm.py` | HD wallet, kiểm tra chain/contract, journal lưu giao dịch đã ký trước broadcast, giữ nonce khi retry, kiểm tra receipt/finality |
| Chữ ký webhook | `app/escrow/webhook.py` | HMAC-SHA256 trên `timestamp.body`; cửa sổ chống phát lại 300 giây; caller deduplicate event ID |
| ABI | `contracts/abi/` | Xuất trực tiếp từ bản biên dịch, không tự viết giả ABI |

Các role `DEFAULT_ADMIN_ROLE`, `RELAYER_ROLE`, `ARBITER_ROLE` tách quyền vận hành. Chỉ relayer đã được cấp quyền có thể xác nhận sự kiện nghiệp vụ; hợp đồng kiểm tra cổng giá/khởi hành/hoàn thành/giải ngân và bảo toàn tiền. Hợp đồng không tự chứng minh việc xe thực sự chở khách: đây là ranh giới tin cậy của backend theo thiết kế custodial.

## Máy trạng thái và hạch toán

1. `DEPOSIT_*` tạo `DEPOSITED`; từ chối booking trùng, địa chỉ không hợp lệ và giá không là bội số 1.000 VND. Booking Pool ghi thêm `quote_vnd` và `target_driver_vnd`.
2. `LOCK` cho Pool ghi giá khóa một lần và hoàn ngay `cap - final`. Ghép thành công không được thu quá quote; tài xế phá ghép chỉ thu quote; không ghép do thị trường dùng cap.
3. `START` đánh dấu bắt đầu sau khi tiền đã vào hợp đồng; `COMPLETE` cần `START` và giá đã khóa.
4. `RELEASE` cần hoàn thành và giá khóa. Auto release chỉ mở sau **24 giờ kể từ hoàn thành**, không tính từ lúc đặt xe. Lệnh không thể giải ngân hai lần.
5. `CANCEL` kiểm tra `fee = driver + platform + fund <= số tiền đang giữ`, chuyển phí đến đúng nơi và hoàn phần dư.
6. `TOPUP` chỉ dùng cho ghép liên tỉnh trước khởi hành. Mỗi booking chuyển sang hoa hồng 15%; `REVERT_TOPUP` hoàn phần tăng thêm và trả lại giá/hoa hồng ghế 10% khi một batch góp thêm không thể hoàn tất.
7. `MERGE` chỉ giảm hoặc giữ giá, cập nhật tài xế/chuyến đích và hoàn chênh lệch. Cửa sổ đồng ý gộp 2 giờ và quyền hủy do backend điều phối.
8. `DISPUTE` đóng băng thanh toán; `RESOLVE` chỉ cho arbiter, bắt buộc tổng phân bổ bằng tiền còn giữ.

Các vector kiểm chứng:

| Tình huống | Khách trả | Tài xế | Nền tảng | Quỹ |
|---|---:|---:|---:|---:|
| Xe máy 14 km / 35 phút | 81.000 | 64.800 | 16.200 | 0 |
| Bao xe liên tỉnh 65 km | 637.000 | 541.450 | 95.550 | 0 |
| Ghép A+B | 248.000 | 210.800 | 29.760 | +7.440 |
| A không ghép do thị trường | 174.000 | 155.200 | 26.100 | −7.300 |
| A không ghép do tài xế từ chối | 155.000 | 131.750 | 23.250 | 0 |
| Ghế liên tỉnh sau góp thêm | 318.000 | 270.300 | 47.700 | 0 |

Nếu Quỹ thiếu thanh khoản, `releasePayment` revert toàn bộ, không chuyển một phần tiền rồi bỏ dở. Backend phải giữ job retry/cảnh báo và bổ sung vốn thử nghiệm theo quy trình, không ghi nhận một payout thành công giả. Với hủy muộn sau khi người còn lại đã khóa giá, `PROTECT_LATE_CANCEL` bảo vệ giá cũ và bù thiếu sau khi khấu trừ phần phạt đã trả cho tài xế; `credited_penalty_vnd` là **tổng tích lũy**, không được giảm.

Đẳng thức kiểm toán on-chain:

```text
token.balanceOf(escrow) = totalBookingLiability + guaranteeFundBalance
fare_charged = driver_base + platform_net + fund_contribution
driver_paid = driver_base + guarantee
fund_after = fund_before + fund_contribution − guarantee
```

## Giao diện Python

```python
from app.escrow import EscrowCommand, LocalEscrowAdapter

adapter = LocalEscrowAdapter("var/escrow.sqlite")
receipt = adapter.execute(EscrowCommand(
    operation_id="escrow:booking-a:deposit", action="DEPOSIT_POOL", booking_id="booking-a",
    params={"passenger": "user-a", "driver": "driver-a", "trip_id": "plan-a",
            "service_code": "CAR_URBAN_POOL", "amount_vnd": 174000,
            "quote_vnd": 155000, "target_driver_vnd": 155200},
))
assert receipt.mode == "LOCAL_SIMULATION" and receipt.tx_hash is None
```

`EscrowCommand` gồm `operation_id`, `action`, `booking_id`, `params`; một operation ID dùng lại với payload khác bị từ chối. `EscrowReceipt` gồm `operation_id`, `mode`, `tx_hash`, `status`, `snapshot`, `block_number`. Chỉ `status == CONFIRMED` được dùng cập nhật trạng thái nghiệp vụ. `SUBMITTED` phải được retry/đợi receipt, không được xem là đã nạp tiền.

| Action | Params bổ sung |
|---|---|
| `DEPOSIT_FIXED`, `DEPOSIT_INTERCITY` | `passenger`, `driver`, `trip_id`, `service_code`, `amount_vnd` |
| `DEPOSIT_POOL` | Các trường deposit + `quote_vnd`, `target_driver_vnd` |
| `LOCK` | `final_vnd`, `matched: bool`, `driver_declined: bool` |
| `TOPUP` | `amount_vnd` |
| `REVERT_TOPUP` | Không có |
| `MERGE` | `driver`, `trip_id`, `final_vnd` |
| `START`, `COMPLETE`, `RELEASE`, `DISPUTE` | Không có |
| `CANCEL` | `fee_vnd`, `driver_vnd`, `platform_vnd`, `fund_vnd` |
| `RESOLVE` | `passenger_vnd`, `driver_vnd`, `platform_vnd` |
| `PROTECT_LATE_CANCEL` | `credited_penalty_vnd` tích lũy |

Snapshot dùng chung gồm `status`, `service_code`, `cap_vnd`, `balance_vnd`, `quote_vnd`, `target_driver_vnd`, `final_vnd`, `refunded_vnd`, `driver_paid_vnd`, `platform_paid_vnd`, `fund_contribution_vnd`, `guarantee_vnd`, `price_locked`, `matched`, `driver_declined`, `started`, `completed`, `topup_mode`, `fund_balance_vnd`, `mode`.

EVM yêu cầu `passenger`/`driver` là địa chỉ EVM checksum. Backend ánh xạ UUID người dùng bằng `CustodialWallets.address(user_id)`, không gửi trực tiếp UUID vào ABI. ID booking/chuyến mã hóa bằng SHA-256 của chuỗi UTF-8 `ride-sharing:v9:<id>`; không dùng SHA3-256 hoặc tự thay công thức giữa listener và adapter.

## Outbox, retry và nhất quán dữ liệu

Backend ghi command vào outbox cùng transaction xác nhận booking. Worker gọi adapter rồi chỉ cập nhật DB/sổ cái sau receipt thành công. Nếu chain đã thực thi nhưng worker chết trước commit DB, retry cùng operation ID lấy lại giao dịch cũ; không tạo booking hay payout mới. Journal transaction khóa việc cấp nonce, lưu raw signed transaction trước broadcast; sau timeout phát lại cùng bytes. Giao dịch còn pending quá hạn có thể được thay với **cùng nonce**, fee tăng 15%, tối đa 5 lần. Receipt revert và thiếu finality không được đánh dấu thành công.

Không thể dùng một transaction SQL để commit nguyên tử với blockchain. Vì vậy bắt buộc giữ journal/outbox sau restart, deduplicate theo operation ID và đối soát fund/booking định kỳ; không xóa journal để “sửa” lỗi tiền. Các command phụ thuộc cần worker xử lý theo thứ tự nghiệp vụ hoặc retry cho đến khi tiền đề tồn tại.

Góp thêm phải có 100% ACCEPT trước khi gửi bất kỳ `TOPUP`. Nếu một booking nạp thất bại sau khi booking khác đã nạp, backend phải dùng `REVERT_TOPUP` cho các phần đã nạp trước khi cho chạy dưới ngưỡng với giá cũ, hoặc hủy hệ thống và hoàn 100% toàn bộ tiền đang giữ. Không được giữ mức hoa hồng 15% khi đã hoàn tiền tăng thêm.

## Chạy kiểm thử local, không deploy bên ngoài

Yêu cầu Node.js 22.13+ và môi trường Python đã cài `web3`, `eth-account`, `pytest`.

```powershell
cd contracts
npm.cmd ci
npm.cmd test
npm.cmd run export-abi
cd ..
.venv/Scripts/python.exe -m pytest tests/escrow -q
.venv/Scripts/python.exe contracts/scripts/verify_adapter.py
```

`verify_adapter.py` tạo mnemonic thử nghiệm mới trong bộ nhớ, khởi động một EVM trên localhost/cổng tạm, deploy hai hợp đồng chỉ vào chain 31337, kiểm tra năm operation qua Web3 và retry cùng transaction hash rồi tắt node. Không đọc khóa production, không ghi mnemonic vào repository và không deploy testnet. Script deploy thủ công `npm.cmd run deploy:local` cũng khóa chain ID 31337.

Đã thực thi: **19 ca EVM**, **18 ca Python local**, kiểm chứng Python adapter với EVM thật tại localhost (ký quỹ → khóa → start → complete → release, replay/restart). Các số đếm này là kiểm thử phần ký quỹ, không thay thế báo cáo kiểm thử toàn hệ thống.

## Chuẩn bị cho testnet sau này

Chọn mạng EVM thử nghiệm và node RPC; deploy token/escrow, cấp role relayer và arbiter, nạp seed Quỹ 5.000.000 tín dụng, cấp gas/token thử cho ví hành khách và phê duyệt allowance token cho hợp đồng. Lưu các biến môi trường qua secret manager:

```text
ESCROW_RELAYER_PRIVATE_KEY=<secret; không đặt trong git hoặc chat>
ESCROW_HD_MNEMONIC=<secret; không đặt trong git hoặc chat>
RPC_URL=<testnet RPC>
CHAIN_ID=<chain ID đã xác nhận>
ESCROW_ADDRESS=<địa chỉ hợp đồng đã xác nhận>
```

Tạo `EvmSettings` bằng RPC, chain ID, địa chỉ, đường dẫn ABI và journal riêng. Adapter kiểm tra đúng chain và địa chỉ có bytecode trước khi ký. HD-wallet journal giữ ánh xạ user→index, không chứa mnemonic. Phải sao lưu mapping cùng DB ứng dụng; mất mapping có thể làm sai địa chỉ người nhận khi khôi phục.

Kiểm tra allowance và số dư gas trước khi đưa ví vào vận hành. Backend không tự mint tín dụng hay chuyển gas trên testnet nếu operator chưa thiết lập. Không có bằng chứng deploy/testnet công khai trong bản bàn giao này theo yêu cầu hoãn deploy của chủ dự án.

## Dependency và giới hạn bảo mật

Solidity dùng OpenZeppelin 5.6.1 (`SafeERC20`, `AccessControl`, `ReentrancyGuard`), compiler npm ghim 0.8.38, Hardhat 3.21.1. Bản lock chứa dependency dev `zod` 3.25.76 do Hardhat/plugin yêu cầu. Tại thời điểm kiểm tra, npm báo 5 mục mức high phát sinh từ một advisory về memory exhaustion khi kiểm tra collection quá lớn trong Zod; dependency production của gói contracts bằng 0 và `npm audit --omit=dev` không có advisory. Không ép override sang Zod 4 vì Hardhat đang dùng API Zod 3; làm vậy có thể phá validation và che rủi ro.

Rủi ro này thuộc CLI build/test nhận cấu hình do operator kiểm soát; không đưa Hardhat/node phát triển lên public internet và không chạy cấu hình hoặc plugin từ nguồn không tin cậy. Cần nâng toolchain khi upstream phát hành bản tương thích đã sửa. Đây là giới hạn đã ghi nhận, không phải tuyên bố “không có lỗ hổng”.

Nguồn kỹ thuật chính: [Hardhat configuration](https://hardhat.org/docs/reference/configuration), [Hardhat migration](https://hardhat.org/docs/migrate-from-hardhat2), [OpenZeppelin ERC20](https://docs.openzeppelin.com/contracts/5.x/api/token/erc20), [Zod advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5). Kết luận dependency dựa trên kết quả audit của lockfile thực tế, cần kiểm tra lại khi upstream thay đổi.
