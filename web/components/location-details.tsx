import type { Point } from "@/lib/types";

export function LocationDetails({
  point,
  title,
}: {
  point?: Point;
  title?: string;
}) {
  if (!point) return null;
  return (
    <div className="location-detail">
      {title && <span>{title}</span>}
      <strong>
        {point.label || `${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}`}
      </strong>
      {point.label && (
        <small>
          Tọa độ: {point.lat.toFixed(5)}, {point.lon.toFixed(5)}
        </small>
      )}
    </div>
  );
}
