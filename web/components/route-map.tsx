"use client";

import { useEffect, useRef, useState } from "react";
import type { Map as LeafletMap } from "leaflet";
import { MapPin, Maximize2 } from "lucide-react";
import type { Point, RoadRoute } from "@/lib/types";
import {
  initialMapProvider,
  mapProviders,
  nextMapProvider,
  type MapProviderId,
} from "@/lib/map-providers";

export function RouteMap({
  pickup,
  dropoff,
  target,
  onPick,
  route,
}: {
  pickup: Point;
  dropoff: Point;
  target?: "pickup" | "dropoff";
  onPick?: (point: Point, target?: "pickup" | "dropoff") => void;
  route?: RoadRoute;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null);
  const pickRef = useRef(onPick);
  const pointsRef = useRef([pickup, dropoff]);
  pointsRef.current = [pickup, dropoff];
  const routeRef = useRef(route);
  routeRef.current = route;
  const fit = (instance: LeafletMap, padding: number = 52) => {
    const [a, b] = pointsRef.current;
    const bounds: [number, number][] = [
      [a.lat, a.lon],
      [b.lat, b.lon],
    ];
    for (const [lon, lat] of routeRef.current?.geometry.coordinates ?? [])
      bounds.push([lat, lon]);
    if (bounds.every((p) => p.every(Number.isFinite)))
      instance.fitBounds(bounds, {
        paddingTopLeft: [padding, 170],
        paddingBottomRight: [padding, 75],
        maxZoom: 16,
        animate: false,
      });
  };
  const fitRef = useRef(fit);
  fitRef.current = fit;
  const [failed, setFailed] = useState(false);
  const [mapReady, setMapReady] = useState(false);
  const [providerId, setProviderId] =
    useState<MapProviderId>(initialMapProvider);
  const [tileStatus, setTileStatus] = useState<
    "loading" | "ready" | "partial" | "error"
  >("loading");
  const [retryVersion, setRetryVersion] = useState(0);
  const triedProviders = useRef(new Set<MapProviderId>([providerId]));
  useEffect(() => {
    pickRef.current = onPick;
  }, [onPick]);
  useEffect(() => {
    let cancelled = false;
    let dispose: (() => void) | undefined;
    import("leaflet")
      .then((L) => {
        if (cancelled || !container.current) return;
        const instance = L.map(container.current, {
          zoomControl: false,
          attributionControl: true,
          zoomAnimation: false,
          fadeAnimation: false,
          markerZoomAnimation: false,
        }).setView([21.01, 105.81], 12);
        map.current = instance;
        setMapReady(true);
        L.control.zoom({ position: "bottomright" }).addTo(instance);
        instance.on(
          "click",
          (event: { latlng: { lat: number; lng: number } }) =>
            pickRef.current?.({
              lat: Number(event.latlng.lat.toFixed(6)),
              lon: Number(event.latlng.lng.toFixed(6)),
            }),
        );
        let resizeFrame = 0;
        const observer = new ResizeObserver(() => {
          cancelAnimationFrame(resizeFrame);
          resizeFrame = requestAnimationFrame(() => {
            if (cancelled) return;
            instance.invalidateSize({ pan: false });
            fitRef.current(instance);
          });
        });
        observer.observe(container.current);
        dispose = () => {
          observer.disconnect();
          cancelAnimationFrame(resizeFrame);
          instance.remove();
          map.current = null;
        };
      })
      .catch(() => setFailed(true));
    return () => {
      cancelled = true;
      dispose?.();
    };
  }, []);
  useEffect(() => {
    if (!mapReady || !map.current) return;
    let cancelled = false;
    let remove: (() => void) | undefined;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const render = async () => {
      const L = await import("leaflet");
      if (cancelled || !map.current) return;
      const source = mapProviders[providerId];
      const tiles = L.tileLayer(source.url, {
        attribution: source.attribution,
        maxZoom: source.maxZoom,
        referrerPolicy: "strict-origin-when-cross-origin",
        updateWhenIdle: true,
        keepBuffer: 1,
      });
      let loaded = 0,
        errors = 0;
      const unavailable = () => {
        if (cancelled) return;
        const fallback = nextMapProvider(triedProviders.current);
        if (fallback) {
          triedProviders.current.add(fallback);
          setProviderId(fallback);
        } else setTileStatus("error");
      };
      tiles.on("loading", () => {
        loaded = 0;
        errors = 0;
        setTileStatus("loading");
        clearTimeout(timeout);
        timeout = setTimeout(() => {
          if (!loaded) unavailable();
        }, 8000);
      });
      tiles.on("tileload", () => {
        if (cancelled) return;
        loaded += 1;
        setTileStatus(errors ? "partial" : "ready");
      });
      tiles.on("tileerror", () => {
        if (cancelled) return;
        errors += 1;
      });
      tiles.on("load", () => {
        if (cancelled) return;
        clearTimeout(timeout);
        if (loaded) setTileStatus(errors ? "partial" : "ready");
        else if (errors) unavailable();
      });
      setTileStatus("loading");
      tiles.addTo(map.current);
      remove = () => {
        // Leaflet's remove event detaches its map listeners; keep it until removal.
        tiles.remove();
        tiles.off();
      };
    };
    void render().catch(() => {
      if (!cancelled) setTileStatus("error");
    });
    return () => {
      cancelled = true;
      clearTimeout(timeout);
      remove?.();
    };
  }, [mapReady, providerId, retryVersion]);
  useEffect(() => {
    let cancelled = false;
    let remove: (() => void) | undefined;
    const render = async () => {
      const L = await import("leaflet");
      if (cancelled || !map.current) return;
      const layers = L.layerGroup();
      if (
        ![pickup.lat, pickup.lon, dropoff.lat, dropoff.lon].every(
          Number.isFinite,
        )
      )
        return;
      for (const [point, label, css] of [
        [pickup, "A", "pickup"],
        [dropoff, "B", "dropoff"],
      ] as const) {
        const tooltip = document.createElement("span");
        tooltip.textContent = point.label ?? label;
        const marker = L.marker([point.lat, point.lon], {
          title: `${label === "A" ? "Điểm đón" : "Điểm đến"}: ${point.label ?? `${point.lat}, ${point.lon}`}`,
          alt: label === "A" ? "Điểm đón A" : "Điểm đến B",
          draggable: Boolean(pickRef.current),
          icon: L.divIcon({
            className: "map-pin",
            html: `<svg class="${css}" width="36" height="44" viewBox="0 0 36 44" aria-hidden="true"><path d="M18 42C14 36 2 27 2 18a16 16 0 1 1 32 0c0 9-12 18-16 24Z" stroke="white" stroke-width="2"/><text x="18" y="23" text-anchor="middle" fill="white" font-size="15" font-weight="700">${label}</text></svg>`,
            iconSize: [36, 44],
            iconAnchor: [18, 42],
          }),
        })
          .bindTooltip(tooltip)
          .addTo(layers);
        marker.on("dragend", () => {
          const position = marker.getLatLng();
          pickRef.current?.(
            {
              lat: Number(position.lat.toFixed(6)),
              lon: Number(position.lng.toFixed(6)),
            },
            label === "A" ? "pickup" : "dropoff",
          );
        });
      }
      if (route) {
        L.polyline(
          route.geometry.coordinates.map(
            ([lon, lat]) => [lat, lon] as [number, number],
          ),
          {
            color: "#267560",
            weight: 5,
            opacity: 0.9,
            className: "road-route-line",
          },
        ).addTo(layers);
        [pickup, dropoff].forEach((point, index) => {
          const [lon, lat] = route.waypoints[index].location;
          L.polyline(
            [
              [point.lat, point.lon],
              [lat, lon],
            ],
            {
              color: "#76705b",
              weight: 2,
              dashArray: "4 5",
              className: "road-connector",
            },
          ).addTo(layers);
        });
      }
      layers.addTo(map.current);
      fitRef.current(map.current);
      remove = () => {
        layers.remove();
      };
    };
    if (mapReady) void render();
    return () => {
      cancelled = true;
      remove?.();
    };
  }, [
    pickup.lat,
    pickup.lon,
    pickup.label,
    dropoff.lat,
    dropoff.lon,
    dropoff.label,
    mapReady,
    route,
  ]);
  return (
    <div className="map-panel">
      <div
        ref={container}
        className="route-map"
        aria-label="Bản đồ chọn điểm đón và điểm đến"
      />
      {failed && (
        <div className="map-fallback">
          <MapPin size={25} />
          <span>
            Chưa tải được bản đồ.
            <br />
            Bạn vẫn có thể nhập tọa độ trực tiếp.
          </span>
        </div>
      )}
      <label className="map-source-control">
        Nền bản đồ
        <select
          aria-label="Nền bản đồ"
          value={providerId}
          onChange={(event) => {
            const id = event.target.value as MapProviderId;
            triedProviders.current = new Set([id]);
            setProviderId(id);
          }}
        >
          {(Object.keys(mapProviders) as MapProviderId[]).map((id) => (
            <option key={id} value={id}>
              {mapProviders[id].name}
            </option>
          ))}
        </select>
      </label>
      {tileStatus === "loading" && !failed && (
        <p className="map-loading-status" role="status">
          Đang tải bản đồ…
        </p>
      )}
      {(tileStatus === "error" || tileStatus === "partial") && !failed && (
        <div className="map-tile-warning" role="status">
          <span>
            {tileStatus === "partial"
              ? "Một phần bản đồ chưa tải được."
              : "Chưa tải được nền bản đồ. Bạn vẫn có thể chọn địa điểm có sẵn hoặc nhập tọa độ."}
          </span>
          <button
            type="button"
            className="text-button"
            onClick={() => {
              triedProviders.current = new Set([providerId]);
              setRetryVersion((version) => version + 1);
            }}
          >
            Tải lại bản đồ
          </button>
        </div>
      )}
      <div className="map-caption">
        <span className="live-dot" />
        {target
          ? `Chạm bản đồ để chọn ${target === "pickup" ? "điểm đón" : "điểm đến"}`
          : "Hà Nội và các tỉnh lân cận"}
      </div>
      <span className="map-note">
        {route
          ? "Tuyến ô tô · Nét đứt nối ghim tới đường"
          : "Kéo ghim A/B hoặc chạm bản đồ để chọn vị trí"}
      </span>
      <button
        className="map-recenter icon-button"
        aria-label="Xem toàn bộ hành trình"
        onClick={() => map.current && fitRef.current(map.current, 50)}
      >
        <Maximize2 size={16} />
      </button>
    </div>
  );
}
