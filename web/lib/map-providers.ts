export type MapProviderId = "osm-de" | "osm";

export const mapProviders = {
  "osm-de": {
    name: "OpenStreetMap · FOSSGIS",
    url: "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> · Tiles <a href="https://www.openstreetmap.de/germanstyle/">FOSSGIS e.V.</a>',
    maxZoom: 19,
  },
  osm: {
    name: "OpenStreetMap chuẩn",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
    maxZoom: 19,
  },
} as const;

export function initialMapProvider(): MapProviderId {
  return process.env.NEXT_PUBLIC_MAP_PROVIDER === "osm" ? "osm" : "osm-de";
}

export function nextMapProvider(
  tried: ReadonlySet<MapProviderId>,
): MapProviderId | undefined {
  return (Object.keys(mapProviders) as MapProviderId[]).find(
    (id) => !tried.has(id),
  );
}
