/**
 * The app's icons: SVG markup on a 24px grid, drawn with a 1.75px round-cap stroke. One
 * source for React (`<Icon>`) and for Leaflet's HTML markers (`iconSvg`).
 */
const ICONS = {
  // Interface
  pin: '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5V12l3 2"/>',
  walk: '<circle cx="12.5" cy="4.5" r="1.8"/><path d="M9 21l2.2-6.2"/><path d="M15 21l-1.6-4.6-2.2-1.6.9-5.1"/><path d="M7.5 12.5l1.6-3.4 3-1.1 2.1 2.4 2.3 1"/>',
  transit:
    '<rect x="5.5" y="5" width="13" height="12" rx="2.5"/><path d="M5.5 11.5h13"/><path d="M9 14.5h.01M15 14.5h.01"/><path d="M8 20.5l1.5-3.5M16 20.5L14.5 17"/><path d="M9.5 2.5h5M12 2.5V5"/>',
  warning: '<path d="M12 3.5 2.8 19.5h18.4z"/><path d="M12 10v4"/><path d="M12 17h.01"/>',
  sparkle:
    '<path d="M11 3.5l1.9 5.1 5.1 1.9-5.1 1.9L11 17.5l-1.9-5.1L4 10.5l5.1-1.9z"/><path d="M18.5 15v5M16 17.5h5"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  "arrow-left": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  link: '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1"/>',
  external:
    '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>',
  globe:
    '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.5 3.8 5.5 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.5-3.8-9S9.5 5.5 12 3z"/>',
  phone:
    '<path d="M5 4h3.5l1.8 4.5-2.3 1.5a11 11 0 0 0 6 6l1.5-2.3L20 15.5V19a1.5 1.5 0 0 1-1.6 1.5C10.6 20 4 13.4 3.5 5.6A1.5 1.5 0 0 1 5 4z"/>',
  map: '<path d="M9 4.5 3.5 6.5v13l5.5-2 6 2 5.5-2v-13l-5.5 2z"/><path d="M9 4.5v13M15 6.5v13"/>',
  locate:
    '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.5"/><path d="M12 2.5V5M12 19v2.5M2.5 12H5M19 12h2.5"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.4-4.4"/>',
  pencil: '<path d="M4 20l1-4.5L15.5 5a2.1 2.1 0 0 1 3 3L8 18.5z"/><path d="M13.5 7l3 3"/>',
  swap: '<path d="M7 4 4 7l3 3"/><path d="M4 7h12a4 4 0 0 1 4 4"/><path d="M17 20l3-3-3-3"/><path d="M20 17H8a4 4 0 0 1-4-4"/>',
  calendar:
    '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M8.5 3v4M15.5 3v4"/>',
  bed: '<path d="M3 18.5V6"/><path d="M3 14h18v4.5"/><path d="M21 14v-2.5A2.5 2.5 0 0 0 18.5 9H11v5"/><circle cx="7" cy="10.5" r="2"/>',
  star: '<path d="M12 3.8l2.5 5.2 5.7.8-4.1 4 1 5.6L12 16.7l-5.1 2.7 1-5.6-4.1-4 5.7-.8z"/>',
  "chevron-down": '<path d="M6 9l6 6 6-6"/>',
  trash:
    '<path d="M4 7h16M10 11v6M14 11v6"/><path d="M6 7l1 12.5A1.5 1.5 0 0 0 8.5 21h7a1.5 1.5 0 0 0 1.5-1.5L18 7"/><path d="M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
  sunset:
    '<path d="M3 18h18M7 21h10"/><path d="M7.5 18a4.5 4.5 0 0 1 9 0"/><path d="M12 3v6M9 6l3 3 3-3"/>',
  gauge: '<path d="M4.5 17a8.5 8.5 0 1 1 15 0"/><path d="M12 13l3.5-4"/><path d="M12 13h.01"/>',
  // Weather
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  cloud: '<path d="M7 18.5h10a4 4 0 0 0 .6-7.95A5.5 5.5 0 0 0 7.1 9.6 4.5 4.5 0 0 0 7 18.5z"/>',
  "cloud-sun":
    '<path d="M8 3.5v1.2M3.5 8h1.2M4.8 4.8l.9.9M11.2 4.8l-.9.9"/><path d="M5.4 10.6A3 3 0 1 1 10.8 7.4"/><path d="M9 20h8.5a3.5 3.5 0 0 0 .5-6.96A4.8 4.8 0 0 0 9 13.2 3.4 3.4 0 0 0 9 20z"/>',
  rain: '<path d="M7 14.5h10a3.75 3.75 0 0 0 .6-7.45A5.2 5.2 0 0 0 7.2 6.4 4.1 4.1 0 0 0 7 14.5z"/><path d="M8.5 17.5l-1 2.5M12.5 17.5l-1 2.5M16.5 17.5l-1 2.5"/>',
  drizzle:
    '<path d="M7 14.5h10a3.75 3.75 0 0 0 .6-7.45A5.2 5.2 0 0 0 7.2 6.4 4.1 4.1 0 0 0 7 14.5z"/><path d="M8.5 18l-.5 1M12.5 18l-.5 1M16.5 18l-.5 1M10.5 21l-.5 1M14.5 21l-.5 1"/>',
  snow: '<path d="M7 14.5h10a3.75 3.75 0 0 0 .6-7.45A5.2 5.2 0 0 0 7.2 6.4 4.1 4.1 0 0 0 7 14.5z"/><path d="M8.5 18.5h.01M12.5 18.5h.01M16.5 18.5h.01M10.5 21.5h.01M14.5 21.5h.01"/>',
  fog: '<path d="M7 11h10a3.5 3.5 0 0 0 .4-6.97A4.8 4.8 0 0 0 7.3 4.6 3.2 3.2 0 0 0 7 11z"/><path d="M3.5 15h17M5.5 18.5h13M8 22h8"/>',
  storm:
    '<path d="M7 14.5h10a3.75 3.75 0 0 0 .6-7.45A5.2 5.2 0 0 0 7.2 6.4 4.1 4.1 0 0 0 7 14.5z"/><path d="M12.5 15.5l-2 3.5h3l-2 3.5"/>',
  // Places
  museum:
    '<path d="M3 9.5 12 4l9 5.5"/><path d="M4.5 20h15M5 17h14"/><path d="M6.5 10.5v6.5M10 10.5v6.5M14 10.5v6.5M17.5 10.5v6.5"/>',
  gallery:
    '<rect x="3.5" y="4.5" width="17" height="15" rx="1.5"/><path d="m3.5 16 5-5 4 4 2.5-2.5 5.5 5.5"/><circle cx="15.5" cy="9" r="1.5"/>',
  castle:
    '<path d="M4 21V8.5h2.5V11H9V8.5h2.5V11h1V8.5H15V11h2.5V8.5H20V21z"/><path d="M10 21v-4a2 2 0 0 1 4 0v4"/>',
  monument: '<path d="M10 20l.8-14L12 3.5l1.2 2.5.8 14"/><path d="M6.5 20.5h11"/>',
  binoculars:
    '<circle cx="7" cy="15.5" r="3.5"/><circle cx="17" cy="15.5" r="3.5"/><path d="M10.5 15.5h3"/><path d="M4.5 13l2-7.5h2.5l1 7M19.5 13l-2-7.5H15l-1 7"/>',
  church:
    '<path d="M12 2.5v4M10.5 4h3"/><path d="M7 21V11l5-4.5 5 4.5v10"/><path d="M3.5 21v-6.5l3.5-2M20.5 21v-6.5l-3.5-2"/><path d="M10.5 21v-3.5a1.5 1.5 0 0 1 3 0V21"/><path d="M2.5 21h19"/>',
  tree: '<path d="M12 21v-6"/><path d="M12 15c-4 0-6.5-2.3-6.5-5.3 0-2.4 1.6-4 3.4-4.4A4 4 0 0 1 12 3a4 4 0 0 1 3.1 2.3c1.8.4 3.4 2 3.4 4.4 0 3-2.5 5.3-6.5 5.3z"/><path d="M8.5 21h7"/>',
  mask: '<path d="M5 4.5h14v6.5a7 7 0 0 1-14 0z"/><path d="M8.5 9.5h.01M15.5 9.5h.01"/><path d="M9 14a3.5 3.5 0 0 0 6 0"/>',
  basket:
    '<path d="M3.5 9.5h17l-1.8 9a2 2 0 0 1-2 1.5H7.3a2 2 0 0 1-2-1.5z"/><path d="M8 9.5l3-6M16 9.5l-3-6"/><path d="M9 13.5v3M12 13.5v3M15 13.5v3"/>',
  wheel:
    '<circle cx="12" cy="10" r="6.5"/><path d="M12 3.5v13M5.5 10h13M7.4 5.4l9.2 9.2M16.6 5.4l-9.2 9.2"/><path d="M8.5 21l3.5-8 3.5 8M7 21h10"/>',
  utensils:
    '<path d="M7 3v8M5 3v5a2 2 0 0 0 4 0V3M7 11v10"/><path d="M17 21V3c-2 1-3.2 3.5-3.2 7 0 1.7.8 3 3.2 3"/>',
  burger:
    '<path d="M4.5 11a7.5 6 0 0 1 15 0z"/><path d="M4 14.5h16"/><path d="M5 17.5h14a1.5 1.5 0 0 1-1.5 2h-11A1.5 1.5 0 0 1 5 17.5z"/>',
  coffee:
    '<path d="M5 9h11v5a5 5 0 0 1-5 5H10a5 5 0 0 1-5-5z"/><path d="M16 10.5h1.5a2.5 2.5 0 0 1 0 5H16"/><path d="M8.5 3.5c0 1 1 1.5 1 2.5M12 3.5c0 1 1 1.5 1 2.5"/>',
  "ice-cream": '<path d="M8 10.5l4 11 4-11"/><path d="M7.5 10.5a4.5 4.5 0 1 1 9 0z"/>',
  pastry:
    '<path d="M4.5 14.5c1-5 5-8.5 7.5-8.5s6.5 3.5 7.5 8.5c-1.5 1.5-4 2.5-7.5 2.5S6 16 4.5 14.5z"/><path d="M10 6.5l-.8 9.8M14 6.5l.8 9.8"/>',
  cocktail: '<path d="M5 4h14l-7 8z"/><path d="M12 12v8M8 20h8"/>',
  beer: '<path d="M6 7h10v12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2z"/><path d="M16 9.5h1.5a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H16"/><path d="M6 7a2.5 2.5 0 0 1 3-2.4 2.8 2.8 0 0 1 4.6.2A2.3 2.3 0 0 1 16 7"/><path d="M9.5 11v6.5M12.5 11v6.5"/>',
  music:
    '<path d="M9 18V5.5l10-2v12.5"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="16.5" cy="16" r="2.5"/>',
} as const;

export type IconName = keyof typeof ICONS;

/** The icon's inner SVG markup. */
export function iconMarkup(name: IconName): string {
  return ICONS[name];
}

/** A whole `<svg>` element as HTML, for markers that Leaflet draws outside React. */
export function iconSvg(name: IconName, size: number, strokeWidth = 1.75): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;
}
