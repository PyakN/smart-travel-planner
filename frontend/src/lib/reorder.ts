import type { PlanEdit } from "./types";

/** Where a row of a list is, top to bottom, in px. */
export interface Span {
  top: number;
  bottom: number;
}

/** `items` with the one at `from` moved to `to`. */
export function moveItem<T>(items: readonly T[], from: number, to: number): T[] {
  const moved = [...items];
  const [item] = moved.splice(from, 1);
  moved.splice(to, 0, item);
  return moved;
}

/**
 * Where the row dragged from `from` lands with its centre at `y`: past every other row whose
 * centre it is below, and never above `min`.
 */
export function dropIndex(spans: readonly Span[], from: number, y: number, min = 0): number {
  const passed = spans.filter((span, i) => i !== from && (span.top + span.bottom) / 2 < y).length;
  return Math.max(min, passed);
}

/** How far row `index` moves aside while the row at `from` (`height` px) goes to `to`. */
export function rowShift(index: number, from: number, to: number, height: number): number {
  if (from < to && index > from && index <= to) return -height;
  if (to < from && index >= to && index < from) return height;
  return 0;
}

/** How far the row at `from` moves to sit in slot `to`, the rows between moved aside. */
export function slotOffset(spans: readonly Span[], from: number, to: number): number {
  if (to > from) return spans[to].bottom - spans[from].bottom;
  if (to < from) return spans[to].top - spans[from].top;
  return 0;
}

/** How many stops at the head of the day are visited: the others cannot go before them. */
export function visitedLead(stops: readonly { place_id: number }[], visited: ReadonlySet<number>) {
  const lead = stops.findIndex((s) => !visited.has(s.place_id));
  return lead === -1 ? stops.length : lead;
}

/**
 * The day's stops not visited, in their order once the stop at `from` moves to `to` (a day
 * edit's `order`); null when that changes nothing.
 */
export function newOrder(
  stops: readonly { place_id: number }[],
  visited: ReadonlySet<number>,
  from: number,
  to: number,
): number[] | null {
  const open = (list: readonly { place_id: number }[]) =>
    list.filter((s) => !visited.has(s.place_id)).map((s) => s.place_id);
  const before = open(stops);
  const after = open(moveItem(stops, from, to));
  return after.some((id, i) => id !== before[i]) ? after : null;
}

/** Whether a version only puts day `day`'s stops in the traveller's order: they can move again. */
export function onlyReordered(edit: PlanEdit | null, day: number): boolean {
  return (
    edit !== null &&
    edit.kind === "edit" &&
    edit.day === day &&
    edit.order.length > 0 &&
    edit.removed.length === 0 &&
    edit.added.length === 0 &&
    edit.next === null
  );
}
