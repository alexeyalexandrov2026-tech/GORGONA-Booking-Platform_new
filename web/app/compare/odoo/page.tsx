import type { Metadata } from "next";
import { ComparePageTemplate } from "../../../components/compare-page";
import { COMPETITORS } from "../../../components/landing/competitors";

const spec = COMPETITORS.odoo;

export const metadata: Metadata = {
  title: spec.seoTitle,
  description: spec.seoDescription,
  alternates: { canonical: "https://www.amarkal-platform.com/compare/odoo/" },
  robots: { index: true, follow: true },
};

export default function CompareOdooPage() {
  return <ComparePageTemplate spec={spec} />;
}
