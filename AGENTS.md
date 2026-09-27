## Code Style

- When editing files, keep every function above the helpers it calls.
- When extracting helpers from a main or public function, keep the main/public function first and place the new helper below it.
- Before finishing an edit, verify that all functions you added or changed still follow caller-above-callee ordering.
- In migration files, keep the primary migration entrypoint or main backfill function first, with helper functions below it.
- In `RunPython` migrations, always use `db_alias = schema_editor.connection.alias` and run ORM operations through `.using(db_alias)`.
- Prefer simple data-driven mappings over layered helper abstractions when the data set is small and fixed.
- When building `selectbox` or `multiselect` options, prefer pre-rendered mappings like `options = {key: rendered_label}` and `format_func=options.__getitem__`.
- In Django admin, prefer shared link helpers like `list_related_html_url` for related-object changelist links instead of hand-building admin URLs.
- Prefer explicit early-return guards like `if not value: return` over wrapping the main body in conditionals when control flow allows it.
- When a module would otherwise need a `typing.TYPE_CHECKING` guard (e.g. to avoid circular imports for type hints), add `from __future__ import annotations` at the top instead so annotations are lazily evaluated, and use unquoted forward references instead of string literals. Do NOT use `from __future__ import annotations` in FastAPI router modules: FastAPI inspects endpoint signatures at import time to derive dependency injection, request parsing, and OpenAPI schemas, and postponed string annotations can break or change that runtime type resolution
- Always use the virtual environment referenced by `.venv` for Python commands in this repo.
- `.venv` may be either a virtualenv directory or a text file containing the virtualenv name.
- If `.venv` is a file, resolve the env before running Python tools. In this repo, for example, `cat .venv` returns the virtualenv name and the interpreter may live at a path like `/Users/<user>/.virtualenvs/$(cat .venv)/bin/python`.
- Prefer invoking the env's executables directly, for example `/Users/<user>/.virtualenvs/$(cat .venv)/bin/python`, `/Users/<user>/.virtualenvs/$(cat .venv)/bin/pytest`, and `/Users/<user>/.virtualenvs/$(cat .venv)/bin/ruff`.
- Run `ruff` after making code edits and fix any reported issues before finishing.
- Do not push commits or update remote branches without explicit user confirmation.

## Gooey GUI Components

- `gooey-gui/app/components` supports dynamically rendered custom components from the Python render tree.
- For a component to participate in this system, the React component name, the file name, and the render-tree node name must match exactly. Example: `ComposioAuthRequired` lives in `gooey-gui/app/components/ComposioAuthRequired.tsx` and is rendered from Python with `gui.component("ComposioAuthRequired", ...)` or an equivalent wrapper.
- In `gooey-gui/app/components`, define these components with a named export in the form `export function <Name>({ ... }) { ... }`. Do not use `export default` for components that are meant to be resolved dynamically through `app/components/index.ts`.
- After adding a new dynamically rendered component under `gooey-gui/app/components`, add `export * from "./<Name>";` to `gooey-gui/app/components/index.ts`.
- These dynamically rendered components are cross-layer contracts. If you change the React component name or props, update the matching Python `gui.component(...)` call at the same time. If you change the Python render call name or props, update the matching React component signature and usage in the same change.
- The dynamic renderer passes the shared contract `props + children + onChange + state` to these components. Components that need render-tree children or form state should accept those props directly instead of relying on a special-case branch in `gooey-gui/app/renderer.tsx`.
- When nesting Python-rendered UI inside a dynamic component, prefer `with gui.component("Name", ...)` as a context manager on the Python side and render the passed child tree on the React side with `RenderedChildren` from `gooey-gui/app/renderer.tsx`. Do not render raw `children` directly in React; in this system they are render-tree nodes, not normal React children.
- Prefer moving app-specific custom components onto the dynamic component path instead of adding more one-off `case` branches to `gooey-gui/app/renderer.tsx`. Keep only true renderer primitives and special protocol nodes in the explicit switch.

## Gooey UI Library

- `gooey-gui/app/ui` holds the React UI primitives (Button, Menu, Sheet, Dialog, Skeleton, ...) that React components build on. Before hand-rolling a button, dropdown, bottom sheet, modal or loading placeholder inside a component, use or extend the primitive here.
- Import primitives only from `~/ui`, never from a component's own folder.
- Never re-export `app/ui` from `gooey-gui/app/components/index.ts`: everything exported there becomes renderable by name from the Python render tree, and primitives are not render-tree nodes.
- One folder per primitive: `<Name>/<Name>.tsx`, `<Name>/<Name>.css`, `<Name>/<Name>.stories.tsx` and `<Name>/index.ts`. Each `index.ts` and `app/ui/index.ts` list their exports by name (values and `export type`s). Do not use `export *` there.
- Prefix every class with `gooey-ui-` and style only through those classes. Do not use bare-element selectors or Bootstrap class names (`.btn`, `.row`, `.modal`). Use the `--gooey-*` tokens from `app/styles/app.css` instead of raw values. Keep the CSS unlayered, because Bootstrap is unlayered and would beat anything in an `@layer`.
- The page is a single `<form>`, so a bare `<button>` posts the whole page. Buttons default to `type="button"`. A control that must post to the server takes an explicit `submit: { name, value }` or `type="submit"`.
- React is 17 here: no `useId`, `useSyncExternalStore`, `useTransition` or `useDeferredValue`.
- Every primitive gets a story, and behaviour gets a `play` test (keyboard, dismiss, submit). Complex widgets from `app/components` get a story with typed mock props in `<Name>.mocks.ts`, typed against `@gooey-types/*` so that a Python contract change fails `npm run typecheck`.
- Run Storybook with `npm run storybook` in `gooey-gui`. Run `npm run build-storybook` to check that every story still builds.

## New Pages

- If you are asked to create a new page, create a React component for that page, add the corresponding Python route/page entrypoint, and render that React component from the new Python route.
- When the page should live inside the standard Gooey page shell, render the component under `sidebar_page_wrapper` as appropriate instead of building a separate ad hoc layout path.
