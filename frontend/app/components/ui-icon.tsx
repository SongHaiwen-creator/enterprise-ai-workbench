import type { SVGProps } from "react";

const paths = {
  sparkles: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z M20 2v4 M18 4h4",
  book: "M12 5v16 M12 5C9 3 5 3 2 4v15c3-1 7-1 10 2 3-3 7-3 10-2V4c-3-1-7-1-10 1Z",
  shield: "m12 3 8 3v6c0 5-5 8-8 9-3-1-8-4-8-9V6l8-3Z m-4 9 3 3 5-6",
  list: "M8 5h12 M8 12h12 M8 19h12 M3 5h.01 M3 12h.01 M3 19h.01",
  layers: "m12 3 10 5-10 5L2 8l10-5Z M2 12l10 5 10-5 M2 16l10 5 10-5",
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M22 21v-2a4 4 0 0 0-3-3.87 M16 3a4 4 0 0 1 0 8 M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  arrow: "M4 12h16 m-6-6 6 6-6 6",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z M14 2v6h6 M8 13h8 M8 17h6",
  menu: "M4 6h16 M4 12h16 M4 18h16",
  close: "m6 6 12 12 M18 6 6 18",
  home: "m3 10 9-7 9 7 M5 9v12h14V9 M9 21v-7h6v7",
  logout: "M9 4H4v16h5 M9 12h12 m-4-4 4 4-4 4",
  check: "m5 12 4 4L19 6",
} as const;

export type IconName = keyof typeof paths;

export function Icon({ name, ...props }: SVGProps<SVGSVGElement> & { name: IconName }) {
  return <svg className="icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[name]} /></svg>;
}

export function BrandMark() {
  return <svg className="brand-symbol" width="30" height="30" viewBox="0 0 32 32" aria-hidden="true"><path fill="#2563eb" d="m16 1 13 7.5v15L16 31 3 23.5v-15Z" /><path fill="#8ab9ff" d="m16 1 13 7.5-13 7.5L3 8.5Z" /><path fill="#fff" d="m16 10 5.2 3v6L16 22l-5.2-3v-6Z" /></svg>;
}
