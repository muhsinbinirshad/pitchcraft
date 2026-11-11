/* Hand-drawn 24px stroke icons. No icon font or icon package. */

const P: Record<string, React.ReactNode> = {
  plus: <path d="M12 5v14M5 12h14" />,
  history: (<><path d="M3.5 12a8.5 8.5 0 1 0 2.5-6" /><path d="M3 4v4.5h4.5" /><path d="M12 7.5V12l3 2" /></>),
  layers: (<><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 13 9 5 9-5" /></>),
  sliders: (<><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" /></>),
  sparkle: <path d="M12 3c.6 4.8 2.7 7.4 9 9-6.3 1.6-8.4 4.2-9 9-.6-4.8-2.7-7.4-9-9 6.3-1.6 8.4-4.2 9-9Z" />,
  upload: (<><path d="M12 15V4M7.5 8.5 12 4l4.5 4.5" /><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" /></>),
  file: (<><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></>),
  image: (<><rect x="3.5" y="4.5" width="17" height="15" rx="2.5" /><circle cx="9" cy="10" r="1.6" /><path d="m4 18 5-5 4 4 2.5-2.5L20 19" /></>),
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  checkCircle: (<><circle cx="12" cy="12" r="9" /><path d="m8 12.3 2.8 2.8L16.2 9.6" /></>),
  x: <path d="M6 6l12 12M18 6 6 18" />,
  warning: (<><path d="M10.3 4.2 2.8 17.5A2 2 0 0 0 4.5 20.5h15a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z" /><path d="M12 9.5v4M12 17h.01" /></>),
  error: (<><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5M12 16.5h.01" /></>),
  download: (<><path d="M12 4v11M7.5 10.5 12 15l4.5-4.5" /><path d="M4 17v1a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1" /></>),
  chevronDown: <path d="m6 9 6 6 6-6" />,
  chevronLeft: <path d="m15 6-6 6 6 6" />,
  trash: (<><path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13" /><path d="M10 11v5.5M14 11v5.5" /></>),
  star: <path d="m12 3.5 2.6 5.4 5.9.8-4.3 4.1 1 5.9-5.2-2.8-5.2 2.8 1-5.9-4.3-4.1 5.9-.8L12 3.5Z" />,
  refresh: (<><path d="M20 11a8 8 0 0 0-14.6-4.5M4 13a8 8 0 0 0 14.6 4.5" /><path d="M4 4v3.5h3.5M20 20v-3.5h-3.5" /></>),
  send: (<><path d="M4 12 20 4l-4 16-4-7-8-1Z" /><path d="m12 13 8-9" /></>),
  eye: (<><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="3" /></>),
  edit: (<><path d="M4 20h4L19.5 8.5a2.8 2.8 0 0 0-4-4L4 16v4Z" /><path d="m13.5 6.5 4 4" /></>),
  key: (<><circle cx="8" cy="15" r="4.5" /><path d="m11.2 11.8 8.3-8.3M16.5 6.5l2.5 2.5M14 9l2 2" /></>),
  table: (<><rect x="3.5" y="4.5" width="17" height="15" rx="2" /><path d="M3.5 9.5h17M3.5 14.5h17M10 9.5v10" /></>),
  replace: (<><path d="M4 8h11l-3-3M20 16H9l3 3" /></>),
  insert: (<><path d="M5 5h14M5 19h14M12 8.5v7M8.5 12h7" /></>),
  quote: <path d="M7 17c-1.7 0-3-1.3-3-3V11c0-2.8 1.6-4.6 4-5l.5 1.4C7 8 6.6 9 6.6 10H9v7H7Zm9 0c-1.7 0-3-1.3-3-3V11c0-2.8 1.6-4.6 4-5l.5 1.4c-1.5.6-1.9 1.6-1.9 2.6H18v7h-2Z" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  pdf: (<><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" /><path d="M14 3v5h5" /><path d="M8.5 16.5v-4h1.3a1.2 1.2 0 0 1 0 2.4H8.5M13 12.5v4h1a2 2 0 0 0 0-4h-1Z" /></>),
  shield: (<><path d="M12 3 5 6v5.5c0 4.4 3 8 7 9.5 4-1.5 7-5.1 7-9.5V6l-7-3Z" /><path d="m9 12 2.2 2.2L15.5 10" /></>),
  wand: (<><path d="m4 20 11-11M13 7l4 4" /><path d="M17 3v2M21 7h-2M19.5 4.5 18 6M8 3l.5 1.5L10 5l-1.5.5L8 7l-.5-1.5L6 5l1.5-.5L8 3Z" /></>),
  inbox: (<><path d="M3.5 13.5 6 5.5h12l2.5 8V18a2 2 0 0 0-2 2h-13a2 2 0 0 1-2-2v-4.5Z" /><path d="M3.5 13.5H8l1 2h6l1-2h4.5" /></>),
  spinner: <path d="M12 3a9 9 0 1 0 9 9" />,
  help: (<><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01" /></>),
  grid: (<><rect x="4" y="4" width="7" height="7" rx="2" /><rect x="13" y="4" width="7" height="7" rx="2" /><rect x="4" y="13" width="7" height="7" rx="2" /><rect x="13" y="13" width="7" height="7" rx="2" /></>),
  chat: <path d="M5 5h14a1.5 1.5 0 0 1 1.5 1.5v9A1.5 1.5 0 0 1 19 17h-8l-4.5 3.5V17H5a1.5 1.5 0 0 1-1.5-1.5v-9A1.5 1.5 0 0 1 5 5Z" />,
  logout: (<><path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4" /><path d="M10 16.5 5.5 12 10 7.5M5.5 12H15" /></>),
  user: (<><circle cx="12" cy="8.5" r="3.5" /><path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5" /></>),
  users: (<><circle cx="9" cy="8.5" r="3.2" /><path d="M3 19.5c.7-3.2 3.1-5 6-5s5.3 1.8 6 5" /><path d="M15.5 5.5a3 3 0 0 1 0 6M17.5 14.7c1.8.6 3 2.2 3.5 4.8" /></>),
  folder: <path d="M3.5 7a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2V7Z" />,
  calendar: (<><rect x="3.5" y="5" width="17" height="15" rx="2.5" /><path d="M3.5 10h17M8 3v4M16 3v4" /></>),
  tag: (<><path d="M3.5 12.2V5a1.5 1.5 0 0 1 1.5-1.5h7.2L20.5 12 12 20.5 3.5 12.2Z" /><circle cx="8.5" cy="8.5" r="1.5" /></>),
  more: (<><circle cx="12" cy="5.5" r="1.3" fill="currentColor" /><circle cx="12" cy="12" r="1.3" fill="currentColor" /><circle cx="12" cy="18.5" r="1.3" fill="currentColor" /></>),
  copy: (<><rect x="8.5" y="8.5" width="11.5" height="11.5" rx="2" /><path d="M15.5 8.5V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7.5a2 2 0 0 0 2 2h2.5" /></>),
  archive: (<><rect x="3.5" y="4.5" width="17" height="4" rx="1.5" /><path d="M5 8.5V18a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5M10 12.5h4" /></>),
  paperclip: <path d="m20 11.5-7.8 7.8a5 5 0 0 1-7.1-7.1L13 4.4a3.3 3.3 0 0 1 4.7 4.7l-7.8 7.8a1.7 1.7 0 0 1-2.4-2.4l7.1-7.1" />,
  search: (<><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.3-4.3" /></>),
  clock: (<><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>),
  arrowUp: <path d="M12 19V5M6 11l6-6 6 6" />,
  lock: (<><rect x="5" y="10.5" width="14" height="10" rx="2.5" /><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" /></>),
  docText: (<><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" /><path d="M14 3v5h5M8.5 12.5h7M8.5 16h7M8.5 9h2.5" /></>),
  pages: (<><rect x="7" y="3.5" width="11.5" height="15" rx="1.5" /><path d="M4.5 7v12a1.5 1.5 0 0 0 1.5 1.5h9" /></>),
  info: (<><circle cx="12" cy="12" r="9" /><path d="M12 11v5.5M12 7.5h.01" /></>),
  external: (<><path d="M14 4h6v6M20 4l-9 9" /><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" /></>),
  branch: (<><circle cx="6.5" cy="5.5" r="2" /><circle cx="6.5" cy="18.5" r="2" /><circle cx="17.5" cy="8.5" r="2" /><path d="M6.5 7.5v9M17.5 10.5c0 4-5 3.5-9.5 6.5" /></>),
  sun: (<><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2M12 19.5v2M4.6 4.6 6 6M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4" /></>),
  moon: <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />,
  monitor: (<><rect x="3" y="4" width="18" height="12.5" rx="2" /><path d="M8.5 20h7M12 16.5V20" /></>),
  logo: (<><path d="M7 3.5h7l4.5 4.5v12.5H7z" /><path d="M14 3.5V8h4.5" /><path d="M12.5 11.5c.3 2 1.2 3 3.5 3.5-2.3.5-3.2 1.5-3.5 3.5-.3-2-1.2-3-3.5-3.5 2.3-.5 3.2-1.5 3.5-3.5Z" /></>),
};

export type IconName = keyof typeof P;

export function Icon({ name, size = 20, className, fill }: { name: IconName | string; size?: number; className?: string; fill?: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={`icon ${name === "spinner" ? "spin" : ""} ${className || ""}`}
      fill={fill ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {P[name] ?? P.help}
    </svg>
  );
}
