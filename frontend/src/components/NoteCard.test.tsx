import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NoteCardView, parseNote } from "./NoteCard";

const raw = {
  id: "n-1",
  xsec_token: "token-1",
  note_card: {
    display_title: "深夜火锅探店",
    user: { nickname: "老王探店", avatar: "https://cdn/a.png" },
    interact_info: {
      liked_count: "128",
      collected_count: "32",
      comment_count: "7",
    },
    image_list: [
      {
        info_list: [
          { image_scene: "WB_DFT", url: "https://img/1.webp" },
        ],
      },
      {
        info_list: [
          { image_scene: "WB_OTHER", url: "https://img/2.webp" },
        ],
      },
      { info_list: [] },
    ],
    cover: { url_default: "https://cover/1.webp" },
    corner_tag_info: [{ text: "探店" }],
  },
};

describe("NoteCard", () => {
  it("parseNote 归一化小红书返回结构", () => {
    const note = parseNote(raw);

    expect(note.title).toBe("深夜火锅探店");
    expect(note.author.nickname).toBe("老王探店");
    expect(note.stats).toEqual({ liked: 128, collected: 32, comments: 7 });
    expect(note.image_urls).toEqual([
      "https://img/1.webp",
      "https://img/2.webp",
    ]);
    expect(note.cover_url).toBe("https://cover/1.webp");
    expect(note.tags).toEqual(["探店"]);
    expect(note.platform_note_id).toBe("n-1");
    expect(note.xsec_token).toBe("token-1");
  });

  it("渲染标题、作者和图片数量", () => {
    render(<NoteCardView note={parseNote(raw)} />);

    expect(screen.getByText("深夜火锅探店")).toBeInTheDocument();
    expect(screen.getByText("老王探店")).toBeInTheDocument();
    expect(screen.getByText("2 张图片")).toBeInTheDocument();
  });
});
