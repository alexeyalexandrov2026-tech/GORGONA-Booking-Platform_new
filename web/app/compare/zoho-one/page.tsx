import type { Metadata } from "next";
import { ComparePageTemplate } from "../../../components/compare-page";
import { COMPETITORS } from "../../../components/landing/competitors";

const spec = COMPETITORS["zoho-one"];

export const metadata: Metadata = {
  title: spec.seoTitle,
  description: spec.seoDescription,
  alternates: {
    canonical: "https://www.amarkal-platform.com/compare/zoho-one/",
  },
  robots: { index: true, follow: true },
};

export default function CompareZohoOnePage() {
  return <ComparePageTemplate spec={spec} />;
}
