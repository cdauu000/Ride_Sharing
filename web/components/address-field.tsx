"use client";

import { useEffect, useId, useRef, useState } from "react";
import { LoaderCircle, MapPin, Search } from "lucide-react";
import { api } from "@/lib/api";
import type { Point } from "@/lib/types";
import { ErrorNotice } from "./ui";

type AddressResult = Point & {
  id: string;
  label: string;
  kind: "address" | "street" | "place";
};

function selectedText(point: Point): string {
  return point.label ?? `${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}`;
}

export function AddressField({
  label,
  point,
  onChange,
  onEdit,
  active,
  onFocus,
  letter,
  presets,
}: {
  label: string;
  point: Point;
  onChange: (point: Point) => void;
  onEdit: (pending: boolean) => void;
  active: boolean;
  onFocus: () => void;
  letter: string;
  presets: Point[];
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const abort = useRef<AbortController | null>(null);
  const revision = useRef(0);
  const [value, setValue] = useState(() => selectedText(point));
  const [results, setResults] = useState<AddressResult[]>([]);
  const [open, setOpen] = useState(false);
  const [searched, setSearched] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [confirmPin, setConfirmPin] = useState(false);
  useEffect(() => {
    revision.current += 1;
    abort.current?.abort();
    setValue(selectedText(point));
    setResults([]);
    setOpen(false);
    setSearched(false);
    setBusy(false);
    setError(undefined);
    setConfirmPin(false);
  }, [point.lat, point.lon, point.label]);
  useEffect(
    () => () => {
      revision.current += 1;
      abort.current?.abort();
    },
    [],
  );
  const pending = value.trim() !== selectedText(point).trim();
  async function search() {
    const query = value.trim();
    if (query.length < 3) {
      setError(new Error("Nhập ít nhất 3 ký tự, gồm tên đường và khu vực."));
      return;
    }
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    const version = ++revision.current;
    setBusy(true);
    setConfirmPin(false);
    setError(undefined);
    setResults([]);
    setOpen(false);
    try {
      const response = await api<{ items: AddressResult[] }>(
        "/locations/search",
        {
          method: "POST",
          body: JSON.stringify({ query }),
          signal: controller.signal,
        },
      );
      if (version !== revision.current || controller.signal.aborted) return;
      setResults(response.items);
      setSearched(true);
      setOpen(response.items.length > 0);
      setHighlight(response.items.length ? 0 : -1);
      input.current?.focus();
    } catch (caught) {
      if (version === revision.current && !controller.signal.aborted)
        setError(caught);
    } finally {
      if (version === revision.current) setBusy(false);
    }
  }
  function choose(value: Point) {
    revision.current += 1;
    abort.current?.abort();
    setValue(selectedText(value));
    setResults([]);
    setOpen(false);
    setSearched(false);
    setBusy(false);
    setError(undefined);
    setConfirmPin(false);
    onEdit(false);
    onChange(value);
  }
  return (
    <div
      className={`place-field ${active ? "focused" : ""}`}
      onFocus={onFocus}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node))
          setOpen(false);
      }}
    >
      <span className={`point-letter ${letter === "B" ? "destination" : ""}`}>
        {letter}
      </span>
      <div>
        <label htmlFor={id}>{label}</label>
        <div className="address-search-row">
          <input
            id={id}
            ref={input}
            type="text"
            role="combobox"
            aria-label={label}
            autoComplete="off"
            maxLength={250}
            value={value}
            placeholder="Nhập số nhà, tên đường, phường/xã…"
            aria-autocomplete="list"
            aria-expanded={open}
            aria-controls={`${id}-results`}
            aria-activedescendant={
              open && highlight >= 0 ? `${id}-option-${highlight}` : undefined
            }
            aria-describedby={`${id}-hint`}
            onFocus={() => {
              if (results.length) setOpen(true);
            }}
            onChange={(event) => {
              revision.current += 1;
              abort.current?.abort();
              setValue(event.target.value);
              setResults([]);
              setOpen(false);
              setSearched(false);
              setBusy(false);
              setError(undefined);
              setConfirmPin(false);
              onEdit(event.target.value.trim() !== selectedText(point).trim());
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                if (open && results[highlight]) choose(results[highlight]);
                else if (!busy) void search();
              } else if (open && ["ArrowDown", "ArrowUp"].includes(event.key)) {
                event.preventDefault();
                setHighlight(
                  (current) =>
                    (current +
                      (event.key === "ArrowDown" ? 1 : -1) +
                      results.length) %
                    results.length,
                );
              } else if (event.key === "Escape") setOpen(false);
            }}
          />
          <button
            type="button"
            className="icon-button address-search-button"
            disabled={busy}
            aria-label={`Tìm địa chỉ ${label.toLocaleLowerCase("vi-VN")}`}
            onClick={() => void search()}
          >
            {busy ? (
              <LoaderCircle size={17} className="spin" />
            ) : (
              <Search size={17} />
            )}
          </button>
        </div>
        <p id={`${id}-hint`} className="address-hint">
          {busy
            ? "Đang tìm địa chỉ…"
            : pending
              ? "Bấm tìm rồi chọn kết quả để xác định vị trí."
              : "Có thể nhập địa chỉ khác hoặc chọn trên bản đồ."}
        </p>
        {!pending && point.precision === "reference" && (
          <p className="address-reference">
            Vị trí tham khảo từ danh mục bổ sung, chưa xác minh cổng đón. Kéo
            ghim nếu cần.
            {point.source?.startsWith("https://") && (
              <>
                {" "}
                <a href={point.source} target="_blank" rel="noreferrer">
                  Nguồn địa chỉ
                </a>
              </>
            )}
          </p>
        )}
        {open && (
          <ul
            id={`${id}-results`}
            role="listbox"
            aria-label={`Kết quả ${label.toLocaleLowerCase("vi-VN")}`}
            className="address-results"
          >
            {results.map((result, index) => (
              <li
                id={`${id}-option-${index}`}
                key={result.id}
                role="option"
                aria-selected={highlight === index}
                className={highlight === index ? "active" : ""}
                tabIndex={-1}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setHighlight(index)}
                onClick={() => choose(result)}
              >
                <strong>{result.label}</strong>
                <small>
                  {result.precision === "reference"
                    ? "Vị trí tham khảo · Cần kiểm tra ghim"
                    : result.kind === "address"
                      ? "Có số nhà · Kiểm tra ghim trước khi đặt"
                      : "Địa điểm/tuyến đường · Kiểm tra ghim trên bản đồ"}
                </small>
              </li>
            ))}
          </ul>
        )}
        {searched && results.length === 0 && (
          <p className="address-hint" role="status">
            Không tìm thấy địa chỉ. Thử thêm phường/xã, tỉnh/thành hoặc chọn vị
            trí trên bản đồ.
          </p>
        )}
        {searched && results.some((result) => result.source) ? (
          <p className="address-credit">
            Danh mục địa chỉ bổ sung · Xem nguồn sau khi chọn địa chỉ.
          </p>
        ) : (
          searched && (
            <p className="address-credit">
              Dữ liệu ©{" "}
              <a
                href="https://www.openstreetmap.org/copyright"
                target="_blank"
                rel="noreferrer"
              >
                OpenStreetMap
              </a>{" "}
              · Photon
            </p>
          )
        )}
        <ErrorNotice error={error} retry={() => void search()} />
        {pending && value.trim().length >= 3 && (
          <div className="manual-address">
            <button
              type="button"
              className="text-button"
              onClick={() => setConfirmPin(!confirmPin)}
            >
              Gắn địa chỉ đã nhập với ghim hiện tại
            </button>
            {confirmPin && (
              <div
                role="group"
                aria-label={`Xác nhận ghim ${label.toLocaleLowerCase("vi-VN")}`}
                className="manual-address-confirm"
              >
                <p>
                  Địa chỉ: <strong>{value.trim()}</strong>
                </p>
                <p>
                  Vị trí ghim: {selectedText(point)}. Chỉ xác nhận khi ghim trên
                  bản đồ đúng điểm bạn muốn đón/trả.
                </p>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => choose({ ...point, label: value.trim() })}
                >
                  Xác nhận địa chỉ tại ghim này
                </button>
              </div>
            )}
          </div>
        )}
        <details className="sample-places">
          <summary>Địa điểm mẫu</summary>
          <select
            aria-label={`${label}: địa điểm mẫu`}
            value={presets.findIndex(
              (p) => p.lat === point.lat && p.lon === point.lon,
            )}
            onChange={(event) => {
              const value = presets[Number(event.target.value)];
              if (value) choose(value);
            }}
          >
            <option value={-1}>Vị trí đã chọn</option>
            {presets.map((p, index) => (
              <option key={p.label} value={index}>
                {p.label}
              </option>
            ))}
          </select>
        </details>
        <details>
          <summary>
            Tọa độ <MapPin size={11} />
          </summary>
          <div className="coordinate-fields">
            <input
              type="number"
              aria-label={`${label}: vĩ độ`}
              step="any"
              min="-90"
              max="90"
              required
              value={point.lat}
              onChange={(event) => {
                if (event.target.value !== "")
                  choose({
                    ...point,
                    lat: Number(event.target.value),
                    label: "Tọa độ tùy chọn",
                  });
              }}
            />
            <input
              type="number"
              aria-label={`${label}: kinh độ`}
              step="any"
              min="-180"
              max="180"
              required
              value={point.lon}
              onChange={(event) => {
                if (event.target.value !== "")
                  choose({
                    ...point,
                    lon: Number(event.target.value),
                    label: "Tọa độ tùy chọn",
                  });
              }}
            />
          </div>
        </details>
      </div>
    </div>
  );
}
