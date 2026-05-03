import { describe, expect, it } from "vitest";
import { formatResponseBlocks } from "./responseFormatting";

describe("formatResponseBlocks", () => {
  it("splits answer text into paragraphs, bullet lists, and tool disclosure blocks", () => {
    const blocks = formatResponseBlocks(
      [
        "Your sleep dropped after late workouts.",
        "",
        "- Resting heart rate increased",
        "- Sleep duration fell",
        "",
        "Tool and data used",
        "- wearables_data: sleep summaries",
        "- rag_with_rerank: MedRAG/textbooks",
      ].join("\n")
    );

    expect(blocks).toEqual([
      { type: "paragraph", text: "Your sleep dropped after late workouts." },
      {
        type: "list",
        items: ["Resting heart rate increased", "Sleep duration fell"],
      },
      {
        type: "tool",
        title: "Tool and data used",
        items: ["wearables_data: sleep summaries", "rag_with_rerank: MedRAG/textbooks"],
      },
    ]);
  });
});
