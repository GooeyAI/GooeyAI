// The same global stylesheets the app loads, in the same order: Bootstrap first (the app
// takes 5.2.3 from a CDN), then ours on top of it.
import "bootstrap/dist/css/bootstrap.min.css";
import "~/styles/app.css";
import "~/styles/custom.css";

import type { Decorator, Preview } from "@storybook/react";
import { unstable_createRemixStub as createRemixStub } from "@remix-run/testing";
import { action } from "@storybook/addon-actions";
import { AppShellProvider } from "~/appShellContext";

/** Every page is one `<form id="gooey-form">` that posts on each interaction. Here the post
 *  goes to the Actions panel instead, with the name/value of the button that sent it. */
const withGooeyForm: Decorator = (Story) => (
  <form
    id="gooey-form"
    onSubmit={(e) => {
      e.preventDefault();
      const submitter = (e.nativeEvent as SubmitEvent)
        .submitter as HTMLButtonElement | null;
      action("gooey-form submit")({
        name: submitter?.name,
        value: submitter?.value,
      });
    }}
  >
    <Story />
  </form>
);

/** Components use Remix's `<Link>` and hooks, which need a router and Remix context. The stub
 *  is rebuilt per render so a changed arg reaches the story - the route element is otherwise
 *  created once and never re-rendered. */
const withRemix: Decorator = (Story) => {
  const RemixStub = createRemixStub([{ path: "*", element: <Story /> }]);
  return <RemixStub />;
};

const withAppShell: Decorator = (Story) => (
  <AppShellProvider>
    <Story />
  </AppShellProvider>
);

const preview: Preview = {
  // Outermost last: the Remix stub wraps the app shell, which wraps the form.
  decorators: [withGooeyForm, withAppShell, withRemix],
  parameters: {
    layout: "padded",
    controls: { expanded: true },
    backgrounds: {
      default: "page",
      values: [
        { name: "page", value: "#fffefd" },
        { name: "rail", value: "#fbfaf8" },
      ],
    },
    viewport: {
      viewports: {
        phone: {
          name: "Phone (390)",
          styles: { width: "390px", height: "844px" },
          type: "mobile",
        },
        tablet: {
          name: "Below lg (991)",
          styles: { width: "991px", height: "900px" },
          type: "tablet",
        },
        desktop: {
          name: "Desktop (1280)",
          styles: { width: "1280px", height: "800px" },
          type: "desktop",
        },
      },
    },
  },
};

export default preview;
