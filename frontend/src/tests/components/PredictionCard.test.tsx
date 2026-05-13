import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PredictionCard, type PredictionResult } from "@/components/product/PredictionCard";
import { bandFor } from "@/components/ui/Gauge";
import enMessages from "../../../messages/en.json";

const M = enMessages.prediction;

function makeResult(r2: number): PredictionResult {
  return {
    target: "amount",
    model: "LinearRegression",
    metrics: { r2, mae: 1.2, n_train: 100, n_test: 25 },
    intercept: 0,
    feature_importance: [
      { feature: "qty", coefficient: 1.5, importance: 0.7 },
      { feature: "discount", coefficient: -0.3, importance: 0.2 },
    ],
    feature_ranges: {
      qty: { min: 0, max: 100, mean: 25 },
      discount: { min: 0, max: 0.5, mean: 0.1 },
    },
  };
}

describe("PredictionCard", () => {
  it("renders the confidence percentage from R²", () => {
    render(<PredictionCard title="Predict" result={makeResult(0.82)} />);
    expect(screen.getByLabelText(/82.*100/)).toBeInTheDocument();
  });

  it("uses high band (≥70) as green", () => {
    expect(bandFor(85)).toBe("high");
    expect(bandFor(70)).toBe("high");
  });

  it("uses medium band (40–69) as yellow", () => {
    expect(bandFor(55)).toBe("medium");
    expect(bandFor(40)).toBe("medium");
    expect(bandFor(69)).toBe("medium");
  });

  it("uses low band (<40) as red", () => {
    expect(bandFor(30)).toBe("low");
    expect(bandFor(0)).toBe("low");
  });

  it("renders translated conditional copy for the confidence band", () => {
    const { rerender } = render(
      <PredictionCard title="P" result={makeResult(0.9)} />,
    );
    expect(screen.getAllByText(M.confidenceHigh).length).toBeGreaterThan(0);
    rerender(<PredictionCard title="P" result={makeResult(0.5)} />);
    expect(screen.getAllByText(M.confidenceMedium).length).toBeGreaterThan(0);
    rerender(<PredictionCard title="P" result={makeResult(0.2)} />);
    expect(screen.getAllByText(M.confidenceLow).length).toBeGreaterThan(0);
  });

  it("includes the translated confidence explanation copy", () => {
    render(<PredictionCard title="P" result={makeResult(0.82)} />);
    expect(screen.getByText(M.confidenceDescription)).toBeInTheDocument();
    expect(screen.getByText(M.topFactors)).toBeInTheDocument();
  });
});
