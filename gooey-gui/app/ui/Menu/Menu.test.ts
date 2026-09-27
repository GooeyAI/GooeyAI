import { describe, expect, it } from "vitest";
import { nextRowIndex } from "./Menu";

describe("nextRowIndex", () => {
  it("wraps ArrowDown past the last row to the first", () => {
    expect(nextRowIndex("ArrowDown", 2, 3)).toBe(0);
  });

  it("wraps ArrowUp past the first row to the last", () => {
    expect(nextRowIndex("ArrowUp", 0, 3)).toBe(2);
  });

  it("starts ArrowUp from the last row when nothing is focused", () => {
    expect(nextRowIndex("ArrowUp", -1, 3)).toBe(2);
  });

  it("jumps with Home and End", () => {
    expect(nextRowIndex("Home", 1, 3)).toBe(0);
    expect(nextRowIndex("End", 1, 3)).toBe(2);
  });

  it("ignores keys that do not navigate", () => {
    expect(nextRowIndex("a", 1, 3)).toBeNull();
  });
});
