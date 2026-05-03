export type ResponseBlock =
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[] }
  | { type: "tool"; title: string; items: string[] };

export function formatResponseBlocks(text: string): ResponseBlock[] {
  const blocks: ResponseBlock[] = [];
  const lines = text.split(/\r?\n/);
  let paragraph: string[] = [];
  let list: string[] = [];
  let toolMode = false;

  function flushParagraph() {
    if (paragraph.length === 0) return;
    blocks.push({ type: "paragraph", text: paragraph.join(" ") });
    paragraph = [];
  }

  function flushList() {
    if (list.length === 0) return;
    if (toolMode) {
      blocks.push({ type: "tool", title: "Tool and data used", items: list });
    } else {
      blocks.push({ type: "list", items: list });
    }
    list = [];
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    if (/^tool and data used:?$/i.test(line)) {
      flushParagraph();
      flushList();
      toolMode = true;
      continue;
    }

    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      list.push(bullet[1]);
      continue;
    }

    flushList();
    paragraph.push(line);
  }

  flushParagraph();
  flushList();
  return blocks;
}
