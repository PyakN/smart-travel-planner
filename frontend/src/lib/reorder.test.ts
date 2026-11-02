import { describe, expect, it } from "vitest";

import {
  type Span,
  dropIndex,
  moveItem,
  newOrder,
  onlyReordered,
  rowShift,
  slotOffset,
  visitedLead,
} from "./reorder";
import type { PlanEdit } from "./types";

// Rows of 100, 50 and 150 px, then 100 px, one under the other.
const SPANS: Span[] = [
  { top: 0, bottom: 100 },
  { top: 100, bottom: 150 },
  { top: 150, bottom: 300 },
  { top: 300, bottom: 400 },
];

const stops = (...ids: number[]) => ids.map((place_id) => ({ place_id }));

describe("moveItem", () => {
  it("moves an item down or up", () => {
    expect(moveItem(["a", "b", "c", "d"], 0, 2)).toEqual(["b", "c", "a", "d"]);
    expect(moveItem(["a", "b", "c", "d"], 3, 1)).toEqual(["a", "d", "b", "c"]);
    expect(moveItem(["a", "b"], 1, 1)).toEqual(["a", "b"]);
  });
});

describe("dropIndex", () => {
  it("lands past the rows whose centres the dragged row is below", () => {
    // Row 0 (centre 50) dragged down to y = 230: past rows 1 (125) and 2 (225).
    expect(dropIndex(SPANS, 0, 230)).toBe(2);
    expect(dropIndex(SPANS, 0, 220)).toBe(1);
    expect(dropIndex(SPANS, 0, 900)).toBe(3);
    expect(dropIndex(SPANS, 3, -50)).toBe(0);
    expect(dropIndex(SPANS, 2, 225)).toBe(2); // where it was
  });

  it("never goes above the first stop it may take", () => {
    expect(dropIndex(SPANS, 3, -50, 1)).toBe(1);
  });
});

describe("rowShift and slotOffset", () => {
  it("moves the rows passed aside by the dragged row's height", () => {
    expect([0, 1, 2, 3].map((i) => rowShift(i, 0, 2, 100))).toEqual([0, -100, -100, 0]);
    expect([0, 1, 2, 3].map((i) => rowShift(i, 3, 1, 100))).toEqual([0, 100, 100, 0]);
  });

  it("puts the dragged row in its slot", () => {
    expect(slotOffset(SPANS, 0, 2)).toBe(200); // under the 50 and 150 px rows
    expect(slotOffset(SPANS, 3, 1)).toBe(-200);
    expect(slotOffset(SPANS, 1, 1)).toBe(0);
  });
});

describe("newOrder", () => {
  it("is the order of the stops not visited, after the move", () => {
    expect(newOrder(stops(1, 2, 3, 4), new Set(), 3, 0)).toEqual([4, 1, 2, 3]);
    expect(newOrder(stops(1, 2, 3, 4), new Set([1]), 1, 3)).toEqual([3, 4, 2]);
  });

  it("is null when the move changes nothing", () => {
    expect(newOrder(stops(1, 2, 3), new Set(), 1, 1)).toBeNull();
    // Past a visited stop only: the others keep their order.
    expect(newOrder(stops(1, 2, 3), new Set([2]), 0, 1)).toBeNull();
  });

  it("knows the visited stops at the head of the day", () => {
    expect(visitedLead(stops(1, 2, 3), new Set([1, 3]))).toBe(1);
    expect(visitedLead(stops(1, 2), new Set([1, 2]))).toBe(2);
    expect(visitedLead(stops(1, 2), new Set())).toBe(0);
  });
});

describe("onlyReordered", () => {
  const edit: PlanEdit = {
    day: 2,
    kind: "edit",
    replaced: [],
    removed: [],
    added: [],
    next: null,
    after: null,
    order: [{ place_id: 4, name: "Sé" }],
    adjustments: [],
    dropped: [],
    warnings: [],
  };

  it("tells a day put in the traveller's order from other changes", () => {
    expect(onlyReordered(edit, 2)).toBe(true);
    expect(onlyReordered(edit, 1)).toBe(false);
    expect(onlyReordered({ ...edit, order: [] }, 2)).toBe(false);
    expect(onlyReordered({ ...edit, removed: [{ place_id: 5, name: "Castelo" }] }, 2)).toBe(false);
    expect(onlyReordered({ ...edit, kind: "replace" }, 2)).toBe(false);
    expect(onlyReordered(null, 2)).toBe(false);
  });
});
