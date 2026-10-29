"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { LogIn, ShieldCheck } from "lucide-react";
import { mutate } from "@/lib/api";
import type { User } from "@/lib/types";
import { ErrorNotice, SubmitButton } from "./ui";

type AuthFields = {
  email: string;
  password: string;
  name: string;
  role: "PASSENGER" | "DRIVER";
  vehicle_type: "BIKE" | "CAR4";
};

export function AuthPanel({
  onAuthenticated,
}: {
  onAuthenticated: (user: User) => void;
}) {
  const [registering, setRegistering] = useState(false);
  const [error, setError] = useState<unknown>();
  const {
    register,
    handleSubmit,
    watch,
    formState: { isSubmitting, errors },
  } = useForm<AuthFields>({
    defaultValues: { role: "PASSENGER", vehicle_type: "CAR4" },
  });
  const role = watch("role");
  async function submit(data: AuthFields) {
    setError(undefined);
    try {
      const user = registering
        ? await mutate<User>("/auth/register", data)
        : await mutate<User>("/auth/login", {
            email: data.email,
            password: data.password,
          });
      onAuthenticated(user);
    } catch (caught) {
      setError(caught);
    }
  }
  return (
    <div className="auth-layout">
      <div className="auth-story">
        <span className="eyebrow light">MỖI HÀNH TRÌNH, THÊM LỰA CHỌN</span>
        <h1>
          Cùng hướng đi.
          <br />
          Chung một hành trình.
        </h1>
        <p>
          Từ một chuyến xe máy nội đô đến hành trình liên tỉnh. Chọn cách đi phù
          hợp, biết rõ mức giá trước khi đặt.
        </p>
        <div className="auth-route">
          <i />
          <div>
            <strong>Điểm bắt đầu</strong>
            <small>Nhu cầu của bạn</small>
          </div>
          <span className="route-dash" />
          <i />
          <div>
            <strong>Điểm đến</strong>
            <small>Một lựa chọn phù hợp hơn</small>
          </div>
        </div>
        <div className="auth-proof">
          <ShieldCheck size={22} />
          <span>
            Giá minh bạch · Ký quỹ theo từng booking
            <br />
            <small>Nguyên mẫu nghiên cứu · Không sử dụng tiền thật</small>
          </span>
        </div>
      </div>
      <div className="auth-card">
        <div className="brand-lockup">
          <span className="brand-mark">cđ</span>
          <span>
            chung đường<small>ĐI CÙNG NHAU, XA HƠN</small>
          </span>
        </div>
        <h2>{registering ? "Bắt đầu hành trình" : "Chào mừng trở lại"}</h2>
        <p>
          {registering
            ? "Tạo tài khoản để khám phá các lựa chọn di chuyển."
            : "Đăng nhập để đặt xe hoặc tiếp tục công việc của bạn."}
        </p>
        <form onSubmit={handleSubmit(submit)}>
          {registering && (
            <label>
              Họ và tên
              <input
                autoComplete="name"
                {...register("name", { required: registering, maxLength: 100 })}
              />
            </label>
          )}
          <label>
            Email
            <input
              type="email"
              autoComplete="email"
              required
              {...register("email", { required: true, maxLength: 254 })}
            />
          </label>
          <label>
            Mật khẩu
            <input
              type="password"
              autoComplete={registering ? "new-password" : "current-password"}
              minLength={registering ? 12 : 1}
              required
              {...register("password", {
                required: true,
                minLength: registering ? 12 : 1,
                maxLength: 128,
              })}
            />
            {registering && (
              <small>
                Ít nhất 12 ký tự. Sử dụng mật khẩu riêng cho tài khoản thử
                nghiệm.
              </small>
            )}
          </label>
          {registering && (
            <label>
              Loại tài khoản
              <select {...register("role")}>
                <option value="PASSENGER">Hành khách</option>
                <option value="DRIVER">Tài xế</option>
              </select>
            </label>
          )}
          {registering && role === "DRIVER" && (
            <label>
              Phương tiện
              <select {...register("vehicle_type")}>
                <option value="CAR4">Taxi 4 ghế hành khách</option>
                <option value="BIKE">Xe máy 1 hành khách</option>
              </select>
            </label>
          )}
          {Object.keys(errors).length > 0 && (
            <p className="field-error" role="alert">
              Vui lòng kiểm tra các thông tin bắt buộc.
            </p>
          )}
          <ErrorNotice error={error} />
          <SubmitButton pending={isSubmitting}>
            {registering ? "Tạo tài khoản" : "Đăng nhập"}
          </SubmitButton>
        </form>
        <button
          className="text-button auth-toggle"
          onClick={() => {
            setRegistering(!registering);
            setError(undefined);
          }}
        >
          <LogIn size={15} />
          {registering
            ? "Đã có tài khoản? Đăng nhập"
            : "Chưa có tài khoản? Đăng ký"}
        </button>
        <p className="auth-footnote">
          Quyền tài xế và quản trị được kiểm tra tại máy chủ. Tài khoản quản trị
          được cấp riêng.
        </p>
        <a className="text-button survey-public-link" href="/survey">
          Tham gia khảo sát ẩn danh · Không cần tài khoản →
        </a>
      </div>
    </div>
  );
}
