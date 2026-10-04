import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "工作台 | 企业 AI 工作台" };

export default function ApplicationLayout({ children }: { children: ReactNode }) {
  return children;
}
