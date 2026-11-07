import type { LinksFunction } from "@remix-run/node";
import { json } from "@remix-run/node"; // Depends on the runtime you choose
import type { ShouldRevalidateFunction } from "@remix-run/react";
import {
  isRouteErrorResponse,
  Links,
  LiveReload,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  useLoaderData,
  useRouteError,
} from "@remix-run/react";
import { captureRemixErrorBoundaryError } from "@sentry/remix";
import { globalProgressStyles, useGlobalProgress } from "~/global-progres-bar";
import {
  HydrationUtilsPostRender,
  HydrationUtilsPreRender,
} from "~/useHydrated";
import settings from "./settings";
import fontAwesomeFreeStyles from "~/styles/fontawesome-free.css";
import type { ReactNode } from "react";

export const links: LinksFunction = () => [
  ...globalProgressStyles(),
  {
    rel: "icon",
    href: "/favicon.ico",
    media: "(prefers-color-scheme: light)",
  },
  {
    rel: "icon",
    href: "/favicon-dark.ico",
    media: "(prefers-color-scheme: dark)",
  },
];

declare global {
  interface Window {
    ENV: typeof settings;
  }
}

// export env vars to the client
export async function loader() {
  return json({
    ENV: {
      SENTRY_DSN: settings.SENTRY_DSN,
      SENTRY_RELEASE: settings.SENTRY_RELEASE,
      SERVER_HOST: settings.SERVER_HOST,
      FONTAWESOME_KIT_URL: settings.FONTAWESOME_KIT_URL,
    },
  });
}

export const shouldRevalidate: ShouldRevalidateFunction = () => false;

export default function App() {
  const { ENV } = useLoaderData<typeof loader>();
  return (
    <Scaffold ENV={ENV}>
      <div
        id="portal"
        style={{ position: "fixed", left: 0, top: 0, zIndex: 9999 }}
      />
      <script
        // load client side env vars
        dangerouslySetInnerHTML={{
          __html: `window.ENV = ${JSON.stringify(ENV)};`,
        }}
      />
      <HydrationUtilsPreRender />
      <Outlet />
      <HydrationUtilsPostRender />
      <ScrollRestoration />
    </Scaffold>
  );
}

function Scaffold({
  children,
  ENV,
}: {
  children?: ReactNode;
  ENV?: Partial<typeof settings>;
}) {
  useGlobalProgress();

  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <Meta />
        <Links />
        {ENV?.FONTAWESOME_KIT_URL ? (
          <script
            src={ENV.FONTAWESOME_KIT_URL}
            crossOrigin="anonymous"
          ></script>
        ) : (
          <link rel="stylesheet" href={fontAwesomeFreeStyles} />
        )}
      </head>
      <body>
        {children}
        <Scripts />
        <LiveReload />
      </body>
    </html>
  );
}

const reloadOnErrors = [
  "TypeError: Failed to fetch",
  "TypeError: Load failed",
  "Network Error",
  "NetworkError",
];

export function ErrorBoundary() {
  const error = useRouteError();

  if (
    reloadOnErrors.some((msg) =>
      `${error}`.toLowerCase().includes(msg.toLowerCase())
    )
  ) {
    window.location.reload();
  }

  captureRemixErrorBoundaryError(error);
  console.error(error);

  // when true, this is what used to go to `CatchBoundary`
  if (isRouteErrorResponse(error)) {
    return (
      <Scaffold>
        <p>Status: {error.status}</p>
        <pre>{JSON.stringify(error.data)}</pre>
      </Scaffold>
    );
  }

  return (
    <Scaffold>
      <h1>Uh oh ...</h1>
      <p>Something went wrong.</p>
      <pre>{`${error}`}</pre>
    </Scaffold>
  );
}
