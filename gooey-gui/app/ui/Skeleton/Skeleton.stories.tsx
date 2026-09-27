import type { Meta, StoryObj } from "@storybook/react";
import { Skeleton } from "./Skeleton";

const meta = {
  title: "UI/Skeleton",
  component: Skeleton,
  args: { shape: "line", lines: 1 },
  argTypes: {
    shape: { control: "inline-radio", options: ["line", "box", "circle"] },
  },
} satisfies Meta<typeof Skeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Playground: Story = {};

export const Paragraph: Story = {
  args: { lines: 4 },
};

/** The fallback a lazily loaded card would show - announced once, on the container. */
export const Card: Story = {
  render: () => (
    <div
      aria-busy="true"
      aria-label="Loading"
      className="d-flex flex-column gap-3 p-3 border rounded-3"
      style={{ maxWidth: 360 }}
    >
      <div className="d-flex align-items-center gap-2">
        <Skeleton shape="circle" />
        <Skeleton width="40%" />
      </div>
      <Skeleton shape="box" height={160} />
      <Skeleton lines={3} />
    </div>
  ),
};
