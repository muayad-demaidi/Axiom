import { describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { DataContextBar } from "@/components/product/DataContextBar";

const datasets = [
  {
    id: 1,
    filename: "sales.csv",
    dataset_name: "sales",
    rows: 1234,
    cols: 8,
    project_id: 1,
  },
];

describe("DataContextBar", () => {
  it("renders the dataset name and row count", () => {
    render(
      <DataContextBar
        projectName="Demo"
        projectId={1}
        datasets={datasets as any}
        activeDatasetId={1}
        streaming={false}
      />,
    );
    expect(screen.getByText("Demo")).toBeInTheDocument();
    expect(screen.getByText(/sales/)).toBeInTheDocument();
    expect(screen.getByText(/1,234/)).toBeInTheDocument();
  });

  it("shows the analyzing pill when streaming is true", () => {
    render(
      <DataContextBar
        projectName="Demo"
        projectId={1}
        datasets={datasets as any}
        activeDatasetId={1}
        streaming
      />,
    );
    expect(screen.getByText(/جاري التحليل/)).toBeInTheDocument();
  });

  it("shows the prediction pill when predictionRunning is true", () => {
    render(
      <DataContextBar
        projectName="Demo"
        projectId={1}
        datasets={datasets as any}
        activeDatasetId={1}
        streaming={false}
        predictionRunning
      />,
    );
    expect(screen.getByText(/جاري التنبؤ/)).toBeInTheDocument();
  });
});
