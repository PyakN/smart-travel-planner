"use client";

import {
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import { type Span, dropIndex, rowShift, slotOffset } from "@/lib/reorder";

// A press that moves less than this is a click, not a drag.
const DRAG_THRESHOLD_PX = 5;
// A drag this close to the top or bottom of the scrolling list scrolls it, up to this fast.
const EDGE_PX = 64;
const MAX_SCROLL_PX = 16;

interface Drag {
  from: number;
  to: number;
  /** How far the pointer has moved the row; null when it sits in slot `to` (keyboard, drop). */
  dy: number | null;
  /** Dropped: waiting for the day to be planned in the new order. */
  dropped: boolean;
  /** The rows as they were when the drag began, in the scroller's content coordinates. */
  spans: Span[];
}

/** A pointer pressed on a handle, followed by the window's listeners. */
interface Press {
  from: number;
  pointerId: number;
  scroller: HTMLElement;
  scrollTop: number;
  startY: number;
  clientY: number;
  spans: Span[];
  /** Moved far enough to be a drag. */
  started: boolean;
  to: number;
  dy: number;
}

function scrollParent(element: HTMLElement): HTMLElement {
  for (let node = element.parentElement; node; node = node.parentElement) {
    const { overflowY } = getComputedStyle(node);
    if ((overflowY === "auto" || overflowY === "scroll") && node.scrollHeight > node.clientHeight) {
      return node;
    }
  }
  return document.scrollingElement as HTMLElement;
}

export interface ReorderOptions {
  /** Rows in the list. */
  count: number;
  /** The first slot a row may move to. */
  min: number;
  /** A row moved from `from` to `to`; the rows stay in their new order until it settles. */
  onDrop: (from: number, to: number) => Promise<unknown> | void;
  /** Spoken as the row moves: "Sé: stop 3 of 5." */
  announce: (message: string) => void;
  /** A row's name, for what is spoken. */
  name: (index: number) => string;
}

/**
 * Moving the rows of a list by dragging a handle (mouse, touch, pen), or with the keyboard:
 * Space or Enter picks a row up, the arrow keys (Home, End) move it, Space or Enter drops it,
 * Escape puts it back. The other rows move aside as it goes; dragged near the edge of the
 * scrolling list, it scrolls.
 */
export function useReorder({ count, min, onDrop, announce, name }: ReorderOptions) {
  const rows = useRef<(HTMLElement | null)[]>([]);
  const [drag, setDrag] = useState<Drag | null>(null);
  const press = useRef<Press | null>(null);
  const [pressing, setPressing] = useState(false);

  function measure(from: number): { scroller: HTMLElement; scrollTop: number; spans: Span[] } {
    const scroller = scrollParent(rows.current[from] as HTMLElement);
    const scrollTop = scroller.scrollTop;
    const spans = rows.current.slice(0, count).map((row) => {
      const rect = (row as HTMLElement).getBoundingClientRect();
      return { top: rect.top + scrollTop, bottom: rect.bottom + scrollTop };
    });
    return { scroller, scrollTop, spans };
  }

  function drop(from: number, to: number, spans: Span[]) {
    if (to === from) {
      setDrag(null);
      return;
    }
    setDrag({ from, to, dy: null, dropped: true, spans });
    announce(`${name(from)} moved to stop ${to + 1}. Planning the day in this order.`);
    // A new plan replaces the list; if none comes, the rows go back.
    void Promise.resolve(onDrop(from, to)).finally(() => setDrag(null));
  }
  // The window's listeners call the latest drop.
  const dropRef = useRef(drop);
  useEffect(() => {
    dropRef.current = drop;
  });

  useEffect(() => {
    const p = press.current;
    if (!pressing || !p) return;
    let frame = 0;
    const box = () =>
      p.scroller === document.scrollingElement
        ? { top: 0, bottom: window.innerHeight }
        : p.scroller.getBoundingClientRect();
    const tick = () => {
      const { top, bottom } = box();
      const above = top + EDGE_PX - p.clientY;
      const below = p.clientY - (bottom - EDGE_PX);
      if (above > 0) p.scroller.scrollTop -= Math.min(MAX_SCROLL_PX, above / 4);
      else if (below > 0) p.scroller.scrollTop += Math.min(MAX_SCROLL_PX, below / 4);
      const dy = p.clientY - p.startY + p.scroller.scrollTop - p.scrollTop;
      const span = p.spans[p.from];
      const to = dropIndex(p.spans, p.from, (span.top + span.bottom) / 2 + dy, min);
      if (dy !== p.dy || to !== p.to) {
        Object.assign(p, { dy, to });
        setDrag({ from: p.from, to, dy, dropped: false, spans: p.spans });
      }
      frame = requestAnimationFrame(tick);
    };
    const move = (event: globalThis.PointerEvent) => {
      if (event.pointerId !== p.pointerId) return;
      p.clientY = event.clientY;
      if (!p.started && Math.abs(p.clientY - p.startY) >= DRAG_THRESHOLD_PX) {
        p.started = true;
        frame = requestAnimationFrame(tick);
      }
    };
    const stop = () => {
      press.current = null;
      setPressing(false);
    };
    const end = (event: globalThis.PointerEvent) => {
      if (event.pointerId !== p.pointerId) return;
      stop();
      if (p.started && event.type === "pointerup") dropRef.current(p.from, p.to, p.spans);
      else setDrag(null);
    };
    const escape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      stop();
      setDrag(null);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
    window.addEventListener("keydown", escape);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      window.removeEventListener("keydown", escape);
    };
  }, [pressing, min]);

  function onPointerDown(event: PointerEvent<HTMLElement>, index: number) {
    if (event.button !== 0 || drag || press.current) return;
    event.preventDefault(); // no text selection while dragging
    const { scroller, scrollTop, spans } = measure(index);
    press.current = {
      from: index,
      pointerId: event.pointerId,
      scroller,
      scrollTop,
      startY: event.clientY,
      clientY: event.clientY,
      spans,
      started: false,
      to: index,
      dy: 0,
    };
    setPressing(true);
  }

  function onKeyDown(event: KeyboardEvent<HTMLElement>, index: number) {
    const { key } = event;
    const pick = key === " " || key === "Enter";
    if (!drag) {
      if (!pick || pressing) return;
      event.preventDefault();
      setDrag({ from: index, to: index, dy: null, dropped: false, spans: measure(index).spans });
      announce(
        `${name(index)} picked up, stop ${index + 1} of ${count}. Move it with the arrow keys, ` +
          "drop it with Space, or put it back with Escape.",
      );
      return;
    }
    if (drag.dropped || drag.dy !== null || drag.from !== index) return;
    const to = {
      ArrowUp: Math.max(min, drag.to - 1),
      ArrowDown: Math.min(count - 1, drag.to + 1),
      Home: min,
      End: count - 1,
    }[key];
    if (to !== undefined) {
      event.preventDefault();
      setDrag({ ...drag, to });
      announce(`${name(index)}: stop ${to + 1} of ${count}.`);
    } else if (pick) {
      event.preventDefault();
      drop(drag.from, drag.to, drag.spans);
    } else if (key === "Escape") {
      event.preventDefault();
      setDrag(null);
      announce(`${name(index)} put back.`);
    }
  }

  /** Leaving a row picked up with the keyboard puts it back. */
  function onBlur(index: number) {
    if (drag && !drag.dropped && drag.dy === null && drag.from === index) setDrag(null);
  }

  /** Where row `index` is drawn while a row moves: aside, or (the moving one) lifted. */
  function rowStyle(index: number): { style?: CSSProperties; lifted: boolean; gliding: boolean } {
    if (!drag) return { lifted: false, gliding: false };
    const { from, to, spans } = drag;
    if (index === from) {
      const dy = drag.dy ?? slotOffset(spans, from, to);
      return {
        style: { transform: `translateY(${dy}px)`, position: "relative", zIndex: 20 },
        lifted: !drag.dropped,
        gliding: drag.dy === null,
      };
    }
    const shift = rowShift(index, from, to, spans[from].bottom - spans[from].top);
    return { style: { transform: `translateY(${shift}px)` }, lifted: false, gliding: true };
  }

  return {
    /** Ref callback for row `index`. */
    row: (index: number) => (element: HTMLElement | null) => {
      rows.current[index] = element;
    },
    rowStyle,
    handle: (index: number) => ({
      onPointerDown: (event: PointerEvent<HTMLElement>) => onPointerDown(event, index),
      onKeyDown: (event: KeyboardEvent<HTMLElement>) => onKeyDown(event, index),
      onBlur: () => onBlur(index),
    }),
    /** A row is moving, or the day is being planned in its new order. */
    active: drag !== null,
    dropped: drag?.dropped ?? false,
    /** The row picked up, if any. */
    moving: drag && !drag.dropped ? drag.from : null,
  };
}
