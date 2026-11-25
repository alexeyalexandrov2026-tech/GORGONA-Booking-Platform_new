import type { Metadata } from "next";
import { SelfServiceOnboarding } from "../../components/self-service-onboarding";

export const metadata: Metadata = {
  title: "Create your business — GORGONA",
  description:
    "Self-service business registration and multi-industry workspace setup.",
};

export default function OnboardingPage() {
  return <SelfServiceOnboarding />;
}
