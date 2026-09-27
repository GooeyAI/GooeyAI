import type { Meta, StoryObj } from "@storybook/react";
import { expect, fn, userEvent, waitFor, within } from "@storybook/test";
import { Button } from "../Button";
import type { ActionEntry } from "../ActionItem";
import { Menu } from "./Menu";

const onVersions = fn();

const WORKFLOW_ITEMS: ActionEntry[] = [
  {
    key: "versions",
    label: "Versions",
    icon: <i className="fa-regular fa-history" />,
    onSelect: onVersions,
  },
  {
    key: "duplicate",
    label: "Duplicate",
    icon: <i className="fa-regular fa-code-fork" />,
    submit: { name: "--recipe-submit-intent", value: "duplicate" },
  },
  { key: "channels", label: "Channels", heading: true },
  {
    key: "whatsapp",
    label: "WhatsApp",
    icon: <i className="fa-brands fa-whatsapp" />,
    href: "/copilot/integrations/",
  },
  {
    key: "slack",
    label: "Slack",
    icon: <i className="fa-brands fa-slack" />,
    disabled: true,
    trailing: <small className="text-muted">Soon</small>,
  },
  {
    key: "delete",
    label: "Delete",
    icon: <i className="fa-solid fa-trash-can" />,
    danger: true,
    onSelect: fn(),
  },
];

const meta = {
  title: "UI/Menu",
  component: Menu,
  args: {
    items: WORKFLOW_ITEMS,
    label: "Workflow menu",
    align: "start",
    trigger: (props) => (
      <Button
        variant="outline"
        icon={<i className="fa-regular fa-ellipsis" />}
        {...props}
      >
        Options
      </Button>
    ),
  },
  argTypes: {
    align: { control: "inline-radio", options: ["start", "end"] },
    items: { control: false },
    trigger: { control: false },
  },
  // room for the menu to open into
  decorators: [(Story) => <div style={{ minHeight: 340 }}>{Story()}</div>],
} satisfies Meta<typeof Menu>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Playground: Story = {};

export const AlignedToEnd: Story = {
  args: { align: "end" },
  decorators: [
    (Story) => <div className="d-flex justify-content-end">{Story()}</div>,
  ],
};

export const OpensAndSelects: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: /options/i }));
    const versions = canvas.getByRole("menuitem", { name: /versions/i });
    // opening focuses the first row, so the keyboard can take it from there
    await waitFor(() => expect(versions).toHaveFocus());
    await userEvent.click(versions);
    await expect(onVersions).toHaveBeenCalled();
    await expect(canvas.queryByRole("menu")).toBeNull();
  },
};

export const KeyboardNavigation: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const trigger = canvas.getByRole("button", { name: /options/i });
    trigger.focus();
    // ArrowUp opens onto the last row
    await userEvent.keyboard("{ArrowUp}");
    await waitFor(() =>
      expect(canvas.getByRole("menuitem", { name: /delete/i })).toHaveFocus()
    );
    // disabled rows are skipped, and the list wraps
    await userEvent.keyboard("{ArrowUp}");
    await expect(
      canvas.getByRole("menuitem", { name: /whatsapp/i })
    ).toHaveFocus();
    await userEvent.keyboard("{End}{ArrowDown}");
    await expect(
      canvas.getByRole("menuitem", { name: /versions/i })
    ).toHaveFocus();
    // Escape closes and hands focus back to the trigger
    await userEvent.keyboard("{Escape}");
    await expect(canvas.queryByRole("menu")).toBeNull();
    await expect(trigger).toHaveFocus();
  },
};

export const ClosesOnOutsideClick: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: /options/i }));
    await expect(canvas.getByRole("menu")).toBeInTheDocument();
    await userEvent.click(canvasElement.ownerDocument.body);
    await expect(canvas.queryByRole("menu")).toBeNull();
  },
};
