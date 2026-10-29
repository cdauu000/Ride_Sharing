const messages: Record<string, string> = {
  ROUTE_PREVIEW_BUSY: "Dịch vụ lộ trình đang bận. Vui lòng chờ giây lát.",
  ROUTE_PREVIEW_UNAVAILABLE:
    "Chưa kết nối được dịch vụ tính đường bộ. Vui lòng thử lại.",
  ROUTE_NOT_FOUND:
    "Không tìm thấy đường ô tô gần hai vị trí này. Kiểm tra lại ghim.",
  SAME_LOCATION: "Điểm đón và điểm đến cần khác nhau.",
  GEOCODER_BUSY: "Dịch vụ tìm địa chỉ đang bận. Vui lòng chờ rồi tìm lại.",
  GEOCODER_UNAVAILABLE:
    "Chưa kết nối được dịch vụ tìm địa chỉ. Bạn có thể thử lại hoặc chọn vị trí trên bản đồ.",
  INVALID_CREDENTIALS:
    "Email hoặc mật khẩu chưa đúng. Vui lòng kiểm tra và thử lại.",
  UNAUTHENTICATED: "Vui lòng đăng nhập để tiếp tục.",
  FORBIDDEN: "Tài khoản này chưa có quyền thực hiện thao tác.",
  NOT_FOUND: "Không tìm thấy chuyến hoặc bạn chưa có quyền xem thông tin này.",
  EMAIL_EXISTS:
    "Email đã được sử dụng. Bạn có thể đăng nhập bằng tài khoản đã có.",
  RATE_LIMITED: "Bạn thao tác quá nhanh. Vui lòng chờ rồi thử lại.",
  RATE_LIMIT_UNAVAILABLE:
    "Bộ kiểm soát truy cập tạm thời chưa sẵn sàng. Vui lòng thử lại sau.",
  NO_SHOW_WAIT_NOT_MET:
    "Chưa đủ thời gian chờ khách. Chỉ xác nhận khách không đến sau 5 phút từ thời điểm đón hợp lệ.",
  ARRIVAL_EVIDENCE_REQUIRED:
    "Vui lòng cập nhật vị trí và xác nhận đã đến điểm đón trước.",
  ARRIVAL_TOO_FAR:
    "Bạn chưa ở gần điểm đón. Hãy cập nhật đúng vị trí hiện tại.",
  DRIVER_NOT_AT_PICKUP:
    "Bạn chưa ở gần điểm đón. Hãy cập nhật đúng vị trí hiện tại.",
  DRIVER_LOCATION_STALE:
    "Vị trí tài xế đã cũ. Hãy cập nhật vị trí trước khi thao tác.",
  TRIP_NOT_READY_TO_DEPART:
    "Chuyến liên tỉnh chưa đến giờ khởi hành hoặc chưa chốt thứ tự đón.",
  ESCROW_NOT_DEPOSITED:
    "Chưa nhận được xác nhận ký quỹ. Hãy chờ cập nhật trước khi bắt đầu chuyến.",
  STALE_CANDIDATE:
    "Phương án đã thay đổi hoặc hết hạn. Vui lòng tìm chuyến lại.",
  STALE_PLAN: "Hành trình đã thay đổi. Vui lòng làm mới danh sách chuyến.",
  REQUEST_ALREADY_BOOKED:
    "Yêu cầu này đã được đặt. Bạn có thể xem tại Hành trình của tôi.",
  OFFER_EXPIRED: "Lời mời đã hết hạn. Vui lòng chờ lời mời mới.",
  DRIVER_NOT_ELIGIBLE:
    "Tài khoản hoặc phương tiện chưa đủ điều kiện nhận chuyến này.",
  KYC_REQUIRED: "Cần xác minh hồ sơ và đúng loại xe trước khi bật dịch vụ này.",
  BOOKING_CLOSED: "Chuyến đã đóng đặt chỗ. Vui lòng chọn chuyến khác.",
  TOPUP_OFFER_EXPIRED: "Đề nghị góp thêm đã hết hạn hoặc đã được trả lời.",
  TOPUP_FUNDING_REQUIRES_RECONCILIATION:
    "Đang xác nhận hoặc hoàn phần góp thêm. Hãy chờ đối soát trước khi quyết định chạy.",
  BOOKING_ALREADY_TERMINAL:
    "Chuyến đã kết thúc hoặc đã hủy; không thể thay đổi thêm.",
  RIDE_NOT_STARTABLE:
    "Chuyến chưa sẵn sàng để bắt đầu hoặc đã được bắt đầu trước đó.",
  RIDE_NOT_STARTED: "Hãy bắt đầu hành trình trước khi xác nhận điểm dừng.",
  STOP_OUT_OF_ORDER: "Vui lòng xác nhận điểm dừng hiện tại theo đúng thứ tự.",
  UNFINISHED_STOPS:
    "Vẫn còn điểm đón/trả chưa hoàn tất. Hãy kiểm tra lại hành trình.",
  GPS_JUMP_REQUIRES_REVIEW:
    "Vị trí thay đổi quá xa so với hành trình. Vui lòng kiểm tra tọa độ.",
  ALREADY_RATED: "Bạn đã gửi đánh giá cho chuyến này.",
  OUT_OF_SERVICE_AREA: "Điểm đón hoặc điểm đến nằm ngoài vùng phục vụ.",
  NO_ROUTE: "Chưa tìm được tuyến đường phù hợp giữa hai điểm.",
  ROUTING_UNAVAILABLE:
    "Dịch vụ định tuyến tạm thời chưa kết nối được. Vui lòng thử lại sau.",
  LOCAL_DEMO_ONLY: "Thao tác này chỉ dùng trong môi trường thử nghiệm cục bộ.",
};

const fields: Record<string, string> = {
  query: "Địa chỉ",
  budget_min: "Ngân sách mong muốn",
  budget_max: "Ngân sách tối đa",
  pickup: "Điểm đón",
  dropoff: "Điểm đến",
  passenger_count: "Số hành khách",
  preferred_departure: "Giờ khởi hành",
  earliest_departure: "Giờ đón sớm nhất",
  latest_departure: "Giờ đón muộn nhất",
  email: "Email",
  password: "Mật khẩu",
  seat_price_vnd: "Giá mỗi ghế",
  departure_time: "Giờ khởi hành",
  pickup_label: "Tên điểm đón",
  dropoff_label: "Tên điểm đến",
};

export function validationMessage(
  issues: { loc?: (string | number)[]; msg?: string; type?: string }[],
): string {
  return issues
    .map((issue) => {
      const name = String(issue.loc?.[1] ?? "");
      const field = fields[name] ?? "Thông tin nhập";
      if (issue.type === "missing") return `${field}: vui lòng nhập thông tin.`;
      if (issue.type === "string_too_long")
        return `${field}: nội dung quá dài.`;
      if (issue.type === "string_too_short")
        return `${field}: nội dung quá ngắn.`;
      if (["greater_than", "greater_than_equal"].includes(issue.type ?? ""))
        return `${field}: giá trị quá nhỏ.`;
      if (["less_than", "less_than_equal"].includes(issue.type ?? ""))
        return `${field}: giá trị quá lớn.`;
      return `${field}: vui lòng kiểm tra giá trị hợp lệ.`;
    })
    .join(" · ");
}

export function userErrorMessage(code: string, fallback?: string): string {
  if (messages[code]) return messages[code];
  if (
    fallback &&
    !/^[A-Z\d_ :.-]+$/.test(fallback) &&
    /[^\x00-\x7F]/.test(fallback)
  )
    return fallback;
  return "Chưa thực hiện được yêu cầu. Vui lòng làm mới dữ liệu và thử lại.";
}
