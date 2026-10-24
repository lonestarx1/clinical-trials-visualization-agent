// 100 questions asked of the production API, with the charts it answered with (public/examples).
import type { Metadata } from "next";
import { DocsTopbar } from "@/components/DocsTopbar";
import { ExamplesBrowser } from "@/components/ExamplesBrowser";

export const metadata: Metadata = {
  title: "Examples · Clinical Trials Explorer",
  description: "100 questions about ClinicalTrials.gov and the charts the Clinical Trials Explorer answered them with.",
};

export default function ExamplesPage() {
  return (
    <div className="app">
      <DocsTopbar />
      <main className="example-page">
        <ExamplesBrowser />
      </main>
    </div>
  );
}
