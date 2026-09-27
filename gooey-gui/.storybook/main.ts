import path from "path";
import type { StorybookConfig } from "@storybook/react-vite";

// The app builds with Remix's own esbuild pipeline; Storybook builds with Vite. The two only
// have to agree on the path aliases in tsconfig.json, which are mirrored here.
const config: StorybookConfig = {
  stories: ["../app/**/*.stories.@(ts|tsx)"],
  addons: ["@storybook/addon-essentials", "@storybook/addon-a11y"],
  framework: { name: "@storybook/react-vite", options: {} },
  core: { disableTelemetry: true },
  viteFinal: async (viteConfig) => {
    viteConfig.resolve ??= {};
    viteConfig.resolve.alias = {
      ...viteConfig.resolve.alias,
      "~": path.resolve(__dirname, "../app"),
      "@gooey-types": path.resolve(__dirname, "../../gooey_gui/types"),
    };
    // Remix's esbuild reads JSX in plain `.js` files (useHydrated.js has some); Vite only
    // looks for it in .jsx/.tsx unless told otherwise. Vite's own default comes first.
    viteConfig.esbuild = {
      ...viteConfig.esbuild,
      include: [/\.(m?ts|[jt]sx)$/, /\/app\/.*\.js$/],
      exclude: [],
      loader: "tsx",
    };
    return viteConfig;
  },
};

export default config;
