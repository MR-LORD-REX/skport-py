# Hosting the documentation

The documentation site is a static browser for the Markdown pages in `docs/`.
It needs no frontend build step. The styles, scripts and Markdown renderer
are served locally, and navigation works under a GitHub Pages repository path.

## Preview locally

From the repository root, start an HTTP server:

```console
python -m http.server 8000 --directory docs
```

Open [http://localhost:8000](http://localhost:8000). Use an HTTP server rather than
opening `index.html` from disk, because the browser fetches Markdown files.

## Deploy with GitHub Actions

1. Push the repository, including `docs/` and `.github/workflows/docs.yml`, to GitHub.
2. Open **Settings → Pages** and select **GitHub Actions** as the source.
3. Push a documentation change to `main` or `master`, or run the **Documentation**
   workflow manually from the Actions tab.
4. Open the URL shown by the deployment job or by **Settings → Pages**.

The workflow uploads `docs/` as the Pages artifact. The `github-pages` environment
uses GitHub's deployment permissions. Update the README's documentation link to
the deployed URL when it is available.

## Deploy from a branch

For a repository using branch-based Pages hosting, select **Deploy from a branch**
in **Settings → Pages**, choose the default branch, and set the folder to `/docs`.
The `.nojekyll` file keeps the published assets unchanged. Use one hosting method
for the repository; disable the Documentation workflow if deploying from a branch.

## Edit and add pages

Edit the Markdown file for an existing page. To add a page, place it in the
appropriate folder and register its title, path and description in
`docs/assets/js/navigation.js`. The navigation order also controls the previous
and next links. Search indexes the registered Markdown pages in the browser.

Use relative Markdown links, such as `../guides/character-builds.md`, so links work
when reading on GitHub and are converted to browser routes by the site. Heading
links also work. Copy a heading's link from the browser for its exact anchor.

## Site behavior

The site supports light and dark themes, keyboard search with **Ctrl K** or
**⌘ K**, copy buttons for fenced examples, and navigation on phones and tablets.
Links use URL hashes, so a shared link or refresh does not require a server
rewrite. Vendor licenses are included beside the local renderer scripts.

See [Publishing releases](publishing.md) to configure package publishing separately.
