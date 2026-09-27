import type { Meta, StoryObj } from "@storybook/react";
import { expect, fn, userEvent, within } from "@storybook/test";
import { RecipeTopBar } from ".";
import {
  ownerTopBar,
  runningTopBar,
  savedRunTopBar,
  visitorTopBar,
} from "./RecipeTopBar.mocks";

// The bar as the page renders it: inside the wrapper base_v2 reserves for it, which is also
// the container its @container rules measure.
const meta = {
  title: "Widgets/RecipeTopBar",
  component: RecipeTopBar,
  args: {
    ...ownerTopBar,
    children: [],
    state: {},
    onChange: fn(),
  },
  parameters: { layout: "fullscreen" },
  decorators: [
    (Story) => (
      <div className="v2-topbar-container flex-shrink-0 w-100 px-2 px-lg-4 py-2">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof RecipeTopBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Owner: Story = {};

export const OwnerPhone: Story = {
  parameters: { viewport: { defaultViewport: "phone" } },
};

export const Running: Story = {
  args: runningTopBar,
};

export const Visitor: Story = {
  args: visitorTopBar,
};

export const VisitorPhone: Story = {
  args: visitorTopBar,
  parameters: { viewport: { defaultViewport: "phone" } },
};

export const SavedRun: Story = {
  args: savedRunTopBar,
};

/** Run posts the page form with the run intent - the Actions panel shows the payload. */
export const RunSubmitsIntent: Story = {
  play: async ({ canvasElement }) => {
    const run = within(canvasElement).getByRole("button", { name: /run/i });
    await expect(run).toHaveAttribute("type", "submit");
    await expect(run).toHaveAttribute("name", ownerTopBar.submit_intent_key);
    await userEvent.click(run);
  },
};
