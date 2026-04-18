import { describe, expect, it } from "vitest";

import { normalizeAssetUrl } from "./assetUrl";

describe("normalizeAssetUrl", () => {
  it("rewrites localhost backend asset urls to same-origin api paths", () => {
    expect(
      normalizeAssetUrl(
        "http://localhost:8888/api/v1/assets/generated-images/main-agent/2026-04-14/img.png",
      ),
    ).toBe(
      "/api/v1/assets/generated-images/main-agent/2026-04-14/img.png",
    );
  });

  it("keeps non-asset urls unchanged", () => {
    expect(normalizeAssetUrl("http://localhost:8888/api/v1/health")).toBe(
      "http://localhost:8888/api/v1/health",
    );
  });
});
