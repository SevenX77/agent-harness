// The app initializes i18n once, at import, before anything renders
// (`main.tsx` → `src/i18n.ts`). A test that renders a component in isolation
// never walks that path, so `useTranslation` would fall back to echoing the key
// and every assertion on visible copy would read `node.editSteps` instead of a
// sentence. Importing it here gives every test the same initialized instance the
// app has, rather than making each test file remember to.
import "./i18n"
