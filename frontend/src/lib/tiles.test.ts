import { describe, expect, it } from "vitest";

import { MAPBOX_STYLE, mapboxFeedbackLink, tileSource } from "./tiles";

describe("tileSource", () => {
  it("uses the public OpenStreetMap server without settings", () => {
    const source = tileSource({});
    expect(source.url).toBe("https://tile.openstreetmap.org/{z}/{x}/{y}.png");
    expect(source.attribution).toContain("OpenStreetMap</a> contributors");
    expect(source).toMatchObject({ tileSize: 256, zoomOffset: 0, minZoom: 0, mapbox: false });
  });

  it("uses a Mapbox style with a token, 512 px tiles one zoom level down", () => {
    const source = tileSource({ mapboxToken: "pk.test+token" });
    expect(source.url).toBe(
      `https://api.mapbox.com/styles/v1/${MAPBOX_STYLE}/tiles/512/{z}/{x}/{y}{r}?access_token=pk.test%2Btoken`,
    );
    expect(source).toMatchObject({ tileSize: 512, zoomOffset: -1, minZoom: 1, mapbox: true });
    expect(source.attribution).toContain('href="https://www.mapbox.com/about/maps/">Mapbox</a>');
    expect(source.attribution).toContain('href="https://www.openstreetmap.org/copyright"');
  });

  it("takes another Mapbox style", () => {
    const source = tileSource({ mapboxToken: "pk.x", mapboxStyle: "me/my-style" });
    expect(source.url).toContain("/styles/v1/me/my-style/tiles/512/");
  });

  it("prefers an explicit tile URL to Mapbox", () => {
    const source = tileSource({
      tileUrl: "https://tiles.example.com/{z}/{x}/{y}.png",
      tileAttribution: "&copy; Example",
      mapboxToken: "pk.x",
    });
    expect(source).toMatchObject({
      url: "https://tiles.example.com/{z}/{x}/{y}.png",
      attribution: "&copy; Example",
      mapbox: false,
    });
  });

  it("reads empty settings as unset", () => {
    // Docker build arguments that were not given arrive as empty strings.
    const source = tileSource({
      tileUrl: "",
      tileAttribution: "",
      mapboxToken: " ",
      mapboxStyle: "",
    });
    expect(source.url).toBe("https://tile.openstreetmap.org/{z}/{x}/{y}.png");
  });
});

describe("mapboxFeedbackLink", () => {
  it("opens the feedback form at the place on the map", () => {
    const link = mapboxFeedbackLink(-9.1393366, 38.7222524, 13.6);
    expect(link).toContain('href="https://apps.mapbox.com/feedback/#/-9.13934/38.72225/14"');
    expect(link).toContain(">Improve this map</a>");
  });
});
