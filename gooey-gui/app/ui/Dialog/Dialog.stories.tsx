import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";
import { expect, fn, userEvent, waitFor, within } from "@storybook/test";
import { Button } from "../Button";
import { ConfirmDialog, Dialog } from "./Dialog";

const meta = {
  title: "UI/Dialog",
  component: Dialog,
  args: {
    open: true,
    title: "Publish changes",
    children:
      "Your changes will be visible to everyone with the link. Earlier versions stay in the history.",
    onDismiss: fn(),
    size: "md",
  },
  argTypes: {
    size: { control: "inline-radio", options: ["sm", "md", "lg"] },
  },
} satisfies Meta<typeof Dialog>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Playground: Story = {
  args: {
    footer: (
      <>
        <Button variant="outline">Cancel</Button>
        <Button>Publish</Button>
      </>
    ),
  },
};

export const NotDismissible: Story = {
  args: {
    dismissible: false,
    title: "Session expired",
    children: "Sign in again to keep working.",
    footer: <Button>Sign in</Button>,
  },
};

/** The dialog lives in the top layer, so queries go through the document, not the canvas. */
export const DismissesOnEscapeAndClose: Story = {
  play: async ({ args, canvasElement }) => {
    const page = within(canvasElement.ownerDocument.body);
    const dialog = await page.findByRole("dialog");
    await waitFor(() => expect(dialog).toHaveAttribute("open"));
    // What the browser fires on Escape. Sent directly: a synthetic keydown is untrusted, and
    // browsers only turn a trusted one into `cancel`.
    dialog.dispatchEvent(new Event("cancel", { cancelable: true }));
    await expect(args.onDismiss).toHaveBeenCalledTimes(1);
    // cancelled, so it is still up until the owner flips `open`
    await expect(dialog).toHaveAttribute("open");
    await userEvent.click(page.getByRole("button", { name: "Close" }));
    await expect(args.onDismiss).toHaveBeenCalledTimes(2);
  },
};

export const Confirm: StoryObj<typeof ConfirmDialog> = {
  render: (args) => <ConfirmDialog {...args} />,
  args: {
    open: true,
    title: "Delete this workflow?",
    children: "This cannot be undone. Runs made with it stay in your history.",
    confirmLabel: "Delete",
    danger: true,
    onConfirm: fn(),
    onDismiss: fn(),
  },
};

/** Confirm posts the page form - see the Actions panel for the name/value it sent. */
export const ConfirmSubmitsForm: StoryObj<typeof ConfirmDialog> = {
  ...Confirm,
  args: {
    ...Confirm.args,
    confirmSubmit: { name: "--menu-delete", value: "confirm" },
  },
};

export const Interactive: Story = {
  render: function Render(args) {
    const [open, setOpen] = useState(false);
    return (
      <>
        <Button onClick={() => setOpen(true)}>Open dialog</Button>
        <Dialog
          {...args}
          open={open}
          onDismiss={() => setOpen(false)}
          footer={
            <>
              <Button variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button onClick={() => setOpen(false)}>Publish</Button>
            </>
          }
        />
      </>
    );
  },
  args: { open: false },
};
