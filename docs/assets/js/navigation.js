export const sections = [
  {
    title: "Start here",
    pages: [
      { id: "overview", title: "Overview", path: "overview.md", description: "Meet the async SKPORT client and choose your first request." },
      { id: "getting-started/installation", title: "Installation", path: "getting-started/installation.md", description: "Install skport-py and prepare your Python environment." },
      { id: "getting-started/account-tokens", title: "Account tokens", path: "getting-started/account-tokens.md", description: "Get an account token from the official SKPORT endpoint and choose public or owner access." },
      { id: "guides/skport-id-and-privacy", title: "SKPORT ID & privacy", path: "guides/skport-id-and-privacy.md", description: "Find your SKPORT ID in the app and configure global and section visibility." },
      { id: "getting-started/quickstart", title: "Quickstart", path: "getting-started/quickstart.md", description: "Fetch your first player profile and character build." },
    ],
  },
  {
    title: "Guides",
    pages: [
      { id: "guides/public-profiles", title: "Public profiles", path: "guides/public-profiles.md", description: "Verify SKPORT IDs, choose game accounts and read profiles." },
      { id: "guides/character-builds", title: "Character builds", path: "guides/character-builds.md", description: "Select operators and use their loadouts and calculated stats." },
      { id: "guides/stat-calculation", title: "Stat calculation", path: "guides/stat-calculation.md", description: "Follow the formulas, rounding rules and validation for static stats." },
      { id: "guides/owner-accounts", title: "Owner accounts", path: "guides/owner-accounts.md", description: "Verify tokens and access an owner's roster and account data." },
      { id: "guides/assets-and-images", title: "Assets & images", path: "guides/assets-and-images.md", description: "Use cached Enka tables and choose SKPORT or Enka artwork." },
      { id: "guides/languages-and-configuration", title: "Configuration", path: "guides/languages-and-configuration.md", description: "Set languages, share clients and configure request behavior." },
      { id: "guides/errors-and-retries", title: "Errors & retries", path: "guides/errors-and-retries.md", description: "Handle missing targets, authentication and partial builds." },
    ],
  },
  {
    title: "Reference",
    pages: [
      { id: "reference/client", title: "SkportClient", path: "reference/client.md", description: "Construction, resource ownership and asset updates." },
      { id: "reference/endfield", title: "Endfield client", path: "reference/endfield.md", description: "Public and owner methods, selectors and return types." },
      { id: "reference/output-models", title: "Output models", path: "reference/output-models.md", description: "Read and serialize player, build, artwork and stat models." },
    ],
  },
  {
    title: "Maintainers",
    pages: [
      { id: "maintainers/hosting", title: "Hosting the docs", path: "maintainers/hosting.md", description: "Preview the site locally and deploy it to GitHub Pages." },
      { id: "maintainers/publishing", title: "Publishing releases", path: "maintainers/publishing.md", description: "Configure trusted publishing and release a version tag." },
    ],
  },
];

export const pages = sections.flatMap((section) => section.pages.map((page) => ({ ...page, section: section.title })));
