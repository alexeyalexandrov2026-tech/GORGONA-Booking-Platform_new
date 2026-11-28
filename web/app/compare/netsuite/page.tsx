import type { Metadata } from "next";
import { ComparePageTemplate } from "../../../components/compare-page";
import { COMPETITORS } from "../../../components/landing/competitors";

const spec = COMPETITORS.netsuite;

export const metadata: Metadata = {
  title: spec.seoTitle,
  description: spec.seoDescription,
  alternates: {
    canonical: "https://www.amarkal-platform.com/compare/netsuite/",
  },
  robots: { index: true, follow: true },
};

export default function CompareNetSuitePage() {
  return <ComparePageTemplate spec={spec} />;
}
