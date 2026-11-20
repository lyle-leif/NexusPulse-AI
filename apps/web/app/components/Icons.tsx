/** Small hand-drawn line icons (24px grid, 1.8 stroke). Decorative: always next to a text label. */
const P = {
  revenue: <><path d="M3 17l5-5 4 4 8-9" /><path d="M15 7h5v5" /></>,
  visits: <><circle cx="9" cy="8" r="3.2" /><path d="M3.5 19c.6-3.2 2.8-5 5.5-5s4.9 1.8 5.5 5" /><circle cx="17" cy="9" r="2.4" /><path d="M16 14.2c2.4.1 4 1.6 4.5 4.3" /></>,
  orders: <><path d="M3 4h2.5l2.2 10.5h10.6L20.5 7H7" /><circle cx="9.5" cy="19" r="1.4" /><circle cx="17" cy="19" r="1.4" /></>,
  conversion: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4.2" /><circle cx="12" cy="12" r="1.2" /></>,
  aov: <><rect x="3" y="6" width="18" height="12" rx="2" /><circle cx="12" cy="12" r="2.6" /><path d="M6.5 9.5v5M17.5 9.5v5" /></>,
  channel: <><circle cx="5" cy="12" r="2" /><circle cx="19" cy="5" r="2" /><circle cx="19" cy="12" r="2" /><circle cx="19" cy="19" r="2" /><path d="M7 12h10M6.6 10.8 17.3 6M6.6 13.2l10.7 4.8" /></>,
  status: <><path d="M3 12h4l2.5-6 5 12 2.5-6h4" /></>,
  issue: <><path d="M12 3.5 21 19.5H3Z" /><path d="M12 10v4.2M12 17v.2" /></>,
  clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>,
  flow: <><path d="M3 6h5c4 0 4 12 8 12h5M3 18h5c1.5 0 2.4-1.6 3.2-3.6M12.8 9.6C13.6 7.6 14.5 6 16 6h5" /></>,
  bridge: <><path d="M4 20V10M9 20V6M14 20v-8M19 20V4" /></>,
  chart: <><path d="M3 20h18" /><path d="M5 16l4-5 4 3 6-8" /></>,
  check: <><circle cx="12" cy="12" r="8.5" /><path d="M8 12.3l2.7 2.7L16.2 9.4" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6" /><path d="M15 15l5.5 5.5" /></>,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8" /></>,
  info: <><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5.5M12 7.6v.2" /></>,
  home: <><path d="M4 11l8-6.5 8 6.5" /><path d="M6 9.8V19h12V9.8" /></>,
  target: <><circle cx="12" cy="12" r="8" /><path d="M12 2.5v4M12 17.5v4M2.5 12h4M17.5 12h4" /><circle cx="12" cy="12" r="2" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" /></>,
  moon: <><path d="M19.5 14.5A8 8 0 0 1 9.5 4.5a8 8 0 1 0 10 10Z" /></>,
} as const;

export type IconName = keyof typeof P;

export default function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {P[name]}
    </svg>
  );
}
