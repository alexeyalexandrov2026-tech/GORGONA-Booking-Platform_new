import type { Metadata } from "next";
import { PublicB2CShop } from "../../components/public-b2c-shop";

export const metadata: Metadata = {
  title: "B2C Storefront — AMARKAL Platform",
  description:
    "Direct-to-customer retail and services storefront with shopping cart, promo codes, and 0%-commission Stripe US checkout.",
  robots: { index: true, follow: true },
};

export default function PublicShopPage() {
  return <PublicB2CShop />;
}
