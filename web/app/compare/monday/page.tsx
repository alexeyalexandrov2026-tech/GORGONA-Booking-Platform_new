import type { Metadata } from "next";
import { ComparePageTemplate } from "../../../components/compare-page";
import { COMPETITORS } from "../../../components/landing/competitors";

const spec = COMPETITORS.monday;

export const metadata: Metadata = {
  title: spec.seoTitle,
  description: spec.seoDescription,
  alternates: { canonical: "https://www.amarkal-platform.com/compare/monday/" },
  robots: { index: true, follow: true },
};

export default function CompareMondayPage() {
  return <ComparePageTemplate spec={spec} />;
}
