import type { Meta, StoryObj } from "@storybook/react";
import { expect, fn, userEvent, within } from "@storybook/test";
import { Link } from "@remix-run/react";
import { Button, buttonClassName } from "./Button";
import type { ButtonSize, ButtonVariant } from "./Button";

const VARIANTS: ButtonVariant[] = ["solid", "outline", "ghost", "danger"];
const SIZES: ButtonSize[] = ["md", "sm"];

const meta = {
  title: "UI/Button",
  component: Button,
  args: {
    children: "Run",
    variant: "solid",
    size: "md",
    onClick: fn(),
  },
  argTypes: {
    variant: { control: "inline-radio", options: VARIANTS },
    size: { control: "inline-radio", options: SIZES },
    icon: { control: false },
  },
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Playground: Story = {
  play: async ({ args, canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button"));
    await expect(args.onClick).toHaveBeenCalledOnce();
  },
};

export const AllVariants: Story = {
  render: () => (
    <div className="d-flex flex-column gap-3">
      {SIZES.map((size) => (
        <div key={size} className="d-flex gap-2 align-items-center">
          {VARIANTS.map((variant) => (
            <Button key={variant} variant={variant} size={size}>
              {variant} {size}
            </Button>
          ))}
        </div>
      ))}
    </div>
  ),
};

export const WithIcon: Story = {
  args: {
    icon: <i className="fa-regular fa-play" />,
    children: "Run",
  },
};

export const IconOnly: Story = {
  render: () => (
    <div className="d-flex gap-2">
      {VARIANTS.map((variant) => (
        <Button
          key={variant}
          variant={variant}
          iconOnly
          aria-label="Share"
          icon={<i className="fa-regular fa-share-nodes" />}
        />
      ))}
    </div>
  ),
};

export const Loading: Story = {
  args: { loading: true, children: "Running" },
  play: async ({ canvasElement }) => {
    const button = within(canvasElement).getByRole("button");
    await expect(button).toBeDisabled();
    await expect(button).toHaveAttribute("aria-busy", "true");
  },
};

export const Disabled: Story = {
  args: { disabled: true },
};

/** Not a submit by default - inside the page form, a bare `<button>` would post the page. */
export const DoesNotSubmitByDefault: Story = {
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole("button")).toHaveAttribute(
      "type",
      "button"
    );
  },
};

/** Opt in to posting the page form; the Actions panel shows the name/value it sent. */
export const Submit: Story = {
  args: {
    type: "submit",
    name: "--recipe-submit-intent",
    value: '{"kind":"run"}',
  },
};

/** `buttonClassName` puts the look on another element - here a Remix Link. */
export const AsLink: Story = {
  render: () => (
    <Link to="/explore/" className={buttonClassName({ variant: "outline" })}>
      Explore
    </Link>
  ),
};
