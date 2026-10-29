import React from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TripForm, places } from "@/components/trip-form";
import { AddressField } from "@/components/address-field";

const address = {
  id: "real-address",
  lat: 21.03881,
  lon: 105.78189,
  label: "144 Xuân Thủy, Cầu Giấy, Hà Nội",
  kind: "address",
};
const response = (data: unknown) =>
  new Response(JSON.stringify(data), { status: 200 });

describe("specific address selection", () => {
  it("accepts a manually entered house address only after explicit pin confirmation", async () => {
    const chosen = vi.fn();
    render(
      <AddressField
        label="Điểm đón"
        point={places[0]}
        onChange={chosen}
        onEdit={() => undefined}
        active
        onFocus={() => undefined}
        letter="A"
        presets={places}
      />,
    );
    fireEvent.change(screen.getByRole("combobox", { name: "Điểm đón" }), {
      target: { value: "Số 7 ngõ nhỏ, Hà Đông, Hà Nội" },
    });
    expect(chosen).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Gắn địa chỉ đã nhập với ghim hiện tại",
      }),
    );
    expect(chosen).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Xác nhận địa chỉ tại ghim này" }),
    );
    expect(chosen).toHaveBeenCalledWith({
      ...places[0],
      label: "Số 7 ngõ nhỏ, Hà Đông, Hà Nội",
    });
  });
  it("does not use the old coordinate while a new address remains unresolved", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    const created = vi.fn();
    render(
      <TripForm
        pickup={places[0]}
        dropoff={places[1]}
        onPickup={() => undefined}
        onDropoff={() => undefined}
        onCreated={created}
        mapTarget="dropoff"
        onMapTarget={() => undefined}
      />,
    );
    fireEvent.change(screen.getByRole("combobox", { name: "Điểm đến" }), {
      target: { value: address.label },
    });
    fireEvent.click(screen.getByRole("button", { name: /Tìm chuyến phù hợp/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "tìm và chọn địa chỉ",
    );
    expect(fetch).not.toHaveBeenCalled();
    expect(created).not.toHaveBeenCalled();
  });

  it("searches only on request and returns the selected result's actual coordinate", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(response({ items: [address] }));
    const chosen = vi.fn(),
      edit = vi.fn();
    render(
      <AddressField
        label="Điểm đến"
        point={places[1]}
        onChange={chosen}
        onEdit={edit}
        active
        onFocus={() => undefined}
        letter="B"
        presets={places}
      />,
    );
    const input = screen.getByRole("combobox", {
      name: "Điểm đến",
    });
    fireEvent.change(input, { target: { value: "144 Xuân Thủy Hà Nội" } });
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(
      await screen.findByRole("option", { name: /144 Xuân Thủy/ }),
    ).toBeVisible();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(chosen).toHaveBeenCalledWith(address);
    expect(edit).toHaveBeenLastCalledWith(false);
    expect(
      JSON.parse((fetch.mock.calls[0][1] as RequestInit).body as string),
    ).toEqual({ query: "144 Xuân Thủy Hà Nội" });
  });

  it("ignores a late result after the address text changes", async () => {
    let resolve!: (response: Response) => void;
    vi.spyOn(globalThis, "fetch").mockImplementation(
      () =>
        new Promise<Response>((done) => {
          resolve = done;
        }),
    );
    const chosen = vi.fn();
    render(
      <AddressField
        label="Điểm đón"
        point={places[0]}
        onChange={chosen}
        onEdit={() => undefined}
        active
        onFocus={() => undefined}
        letter="A"
        presets={places}
      />,
    );
    const input = screen.getByRole("combobox", {
      name: "Điểm đón",
    });
    fireEvent.change(input, { target: { value: "144 Xuân Thủy Hà Nội" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(resolve).toBeDefined());
    fireEvent.change(input, { target: { value: "Địa chỉ khác" } });
    await act(async () => {
      resolve(response({ items: [address] }));
    });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(chosen).not.toHaveBeenCalled();
    expect(input).toHaveValue("Địa chỉ khác");
  });
});
