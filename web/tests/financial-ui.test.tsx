import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CandidateCard } from "@/components/recommendations";
import { TripForm, places } from "@/components/trip-form";
import { AuthPanel } from "@/components/auth-panel";
import type { Candidate } from "@/lib/types";

const poolCandidate: Candidate = {
  id: "pool-1",
  service_code: "CAR_URBAN_POOL",
  matched_estimate: 143000,
  quote: 155000,
  unmatched: 174000,
  pickup_eta_min: 8,
  duration_min: 52,
  p_match_label: "Cao",
};

describe("transparent booking choices", () => {
  it("displays distinct matched estimate, matched guarantee and maximum unmatched obligation", () => {
    render(
      <CandidateCard
        candidate={poolCandidate}
        recommended={true}
        pending={false}
        disabled={false}
        onSelect={() => undefined}
      />,
    );
    expect(screen.getByText("143.000 đ")).toBeInTheDocument();
    expect(screen.getByText("155.000 đ")).toBeInTheDocument();
    expect(screen.getByText("174.000 đ")).toBeInTheDocument();
    expect(screen.getByText("Dự kiến khi ghép được")).toBeInTheDocument();
    expect(screen.getByText("Tối đa khi ghép được")).toBeInTheDocument();
    expect(screen.getByText("Tối đa nếu không ghép")).toBeInTheDocument();
    expect(screen.queryByText(/95%/)).not.toBeInTheDocument();
  });

  it("blocks additional selection while a financial mutation is pending", () => {
    const select = vi.fn();
    render(
      <CandidateCard
        candidate={poolCandidate}
        recommended={false}
        pending={true}
        disabled={true}
        onSelect={select}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Đang giữ chỗ/ }));
    expect(select).not.toHaveBeenCalled();
  });

  it("does not describe private rides as sharing with strangers", () => {
    render(
      <CandidateCard
        candidate={{
          id: "private-1",
          service_code: "CAR_URBAN_PRIVATE",
          price: 194000,
        }}
        recommended={false}
        pending={false}
        disabled={false}
        onSelect={() => undefined}
      />,
    );
    expect(
      screen.getByText("Đi riêng · Không ghép thêm hành khách"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Tối đa nếu không ghép")).not.toBeInTheDocument();
  });

  it("rejects an inverted budget before creating a request", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const created = vi.fn();
    render(
      <TripForm
        pickup={places[0]}
        dropoff={places[1]}
        onPickup={() => undefined}
        onDropoff={() => undefined}
        mapTarget="pickup"
        onMapTarget={() => undefined}
        onCreated={created}
      />,
    );
    fireEvent.change(screen.getByLabelText("Ngân sách mong muốn"), {
      target: { value: "900000" },
    });
    fireEvent.change(screen.getByLabelText("Tối đa có thể trả"), {
      target: { value: "100000" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Tìm chuyến phù hợp/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Ngân sách mong muốn cần nhỏ hơn hoặc bằng ngân sách tối đa",
    );
    expect(created).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("provides vehicle selection when registering as a driver", () => {
    render(<AuthPanel onAuthenticated={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: /Chưa có tài khoản/ }));
    fireEvent.change(screen.getByLabelText("Loại tài khoản"), {
      target: { value: "DRIVER" },
    });
    expect(
      screen.getByRole("option", { name: "Xe máy 1 hành khách" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "Quản trị viên" }),
    ).not.toBeInTheDocument();
  });
});
