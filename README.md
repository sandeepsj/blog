# blog

My blog: things I built, and things I found out while building them. **https://sandeepsj.github.io/blog/**

Plain Jekyll. GitHub Pages builds it from `main`, so there's nothing to install: a post is a Markdown file in
`_posts/YYYY-MM-DD-slug.md`, and pushing publishes it. Drafts live in `_drafts/`, which is gitignored and
never leaves the machine.

## The `blog` skill
`plugin/` is a Claude Code plugin with one skill, **blog**: how to draft, privacy-check, publish and verify a
post here. It's served from my LiteLLM proxy's plugin marketplace, so every machine using that proxy has it:

```
claude plugin marketplace add <litellm>/claude-code/marketplace.json
claude plugin install blog@litellm
```

Without the proxy, this repo is a marketplace too:

```
claude plugin marketplace add sandeepsj/blog
claude plugin install blog@sandeepsj-blog
```
