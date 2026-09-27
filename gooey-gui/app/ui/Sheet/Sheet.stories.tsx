import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";
import { expect, fn, userEvent, within } from "@storybook/test";
import { Button } from "../Button";
import type { ActionEntry } from "../ActionItem";
import { Sheet } from "./Sheet";

const VIEW_ITEMS: ActionEntry[] = [
  { key: "views", label: "Views", heading: true },
  {
    key: "about",
    label: "About",
    icon: <i className="fa-regular fa-circle-info" />,
    onSelect: fn(),
  },
  {
    key: "preview",
    label: "Preview",
    icon: <i className="fa-regular fa-play" />,
    onSelect: fn(),
  },
  {
    key: "edit",
    label: "Edit",
    icon: <i className="fa-regular fa-pencil" />,
    onSelect: fn(),
  },
  { key: "actions", label: "Actions", heading: true },
  {
    key: "share",
    label: "Share",
    icon: <i className="fa-regular fa-share-nodes" />,
    submit: { name: "--recipe-submit-intent", value: '{"kind":"share"}' },
  },
  {
    key: "api",
    label: "API",
    icon: <i className="fa-regular fa-rocket" />,
    href: "/copilot/api/",
  },
];

const meta = {
  title: "UI/Sheet",
  component: Sheet,
  args: {
    open: true,
    label: "Workflow menu",
    items: VIEW_ITEMS,
    onDismiss: fn(),
  },
  argTypes: { items: { control: false } },
  parameters: {
    layout: "fullscreen",
    viewport: { defaultViewport: "phone" },
  },
} satisfies Meta<typeof Sheet>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Open: Story = {};

export const DismissesOnScrimAndEscape: Story = {
  play: async ({ args, canvasElement }) => {
    const dialog = within(canvasElement).getByRole("dialog");
    await userEvent.click(dialog.parentElement!);
    await expect(args.onDismiss).toHaveBeenCalledTimes(1);
    await userEvent.keyboard("{Escape}");
    await expect(args.onDismiss).toHaveBeenCalledTimes(2);
    // a tap inside the panel is not a dismiss
    await userEvent.click(dialog);
    await expect(args.onDismiss).toHaveBeenCalledTimes(2);
  },
};

export const WithCustomContent: Story = {
  args: {
    items: [],
    children: (
      <div className="px-2 pb-2">
        <h3 className="fs-6 fw-semibold">Run settings</h3>
        <p className="text-muted small mb-0">
          Anything can go in a sheet - these rows are just the common case.
        </p>
      </div>
    ),
  },
};

/** Opened from a trigger, the way a page uses it. */
export const Interactive: Story = {
  args: { open: false },
  render: function Render(args) {
    const [open, setOpen] = useState(false);
    return (
      <div className="p-3">
        <Button variant="outline" onClick={() => setOpen(true)}>
          Open sheet
        </Button>
        <Sheet {...args} open={open} onDismiss={() => setOpen(false)} />
      </div>
    );
  },
};
