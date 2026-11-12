---
name: blog
description: Write, publish or edit a post on Sandeep's blog (repo github.com/sandeepsj/blog, site https://sandeepsj.github.io/blog/). Use when the user wants to blog about, write up, or publish something they built or found out ("blog this", "write a post about…", "let's make a blog about this"), or to fix or update an existing post.
---

# Sandeep's blog

A Jekyll site that GitHub Pages builds by itself: no local tooling. Pushing to `main` publishes.

| | |
|---|---|
| Repo | `sandeepsj/blog` (public) |
| Local clone | `~/dev/blog`. If it's missing: `gh repo clone sandeepsj/blog ~/dev/blog` |
| Site | `https://sandeepsj.github.io/blog/` |
| A post's URL | `https://sandeepsj.github.io/blog/YYYY/MM/DD/<slug>/` |

## The workflow

1. **Update the clone first:** `git -C ~/dev/blog pull --ff-only`.
2. **Draft locally.** Write `~/dev/blog/_drafts/<slug>.md` (`_drafts/` is gitignored, so it never leaves the machine). Show the user the draft, or the parts that changed, and iterate until they're happy.
3. **Privacy check, before anything leaves the machine.** Search the draft and every file it adds for:
   - tokens, keys and passwords (`sk-`, `ghp_`, `token=`, `Bearer`, long random strings);
   - secret URLs (for example a Tailscale Funnel link with a secret path), private IPs and hostnames;
   - other people's names, emails and phone numbers, or anything the user said was private;
   - absolute home paths like `/home/<user>/…` (write `~/…`).

   Fix what you find. If unsure, ask.
4. **Publish only when the user says so.** Pushing makes it public, and it may be indexed and cached even if deleted later.
   - Move the draft to `_posts/YYYY-MM-DD-<slug>.md`, using today's date unless the user picks one.
   - Then `git add`, `git commit -m "Post: <title>"`, `git push`.
5. **Verify.** GitHub Pages builds in about a minute:
   ```
   gh api repos/sandeepsj/blog/pages/builds/latest --jq '.status + " " + (.error.message // "")'
   ```
   Wait for `built`, then fetch the post's URL and check it shows the title. If the build `errored`, read the message (usually bad front matter or Liquid in a code block), fix it and push again. Give the user the link.

## A post's file

```markdown
---
layout: post
title: "Kokoro TTS 40% faster on a laptop CPU, same sound"
description: "One sentence: what the reader gets. Shown under the title, on the index, and in link previews."
result: "2.8× → 3.9× real time, audio identical to 97 dB"
project: kokoro
tags: [tts, performance]
---

Body in Markdown (GitHub-flavoured: tables and fenced code work).
```

- **`result`** (optional, but use it whenever there's a measured outcome): the answer in one short line with its numbers. The design draws it as **the boxed answer**, the way engineers box a final result on a computation pad, both on the post and in the index. It's the page's one loud element, so keep it to a single fact; no sentences.
- **`project`** (optional): what it's part of, shown in the post's title block. Defaults to the first tag.
- **Slug:** short, lowercase, hyphens: `kokoro-openvino-decoder`.
- **Images and other files:** put them in `assets/posts/<slug>/` and link with `{{ '/assets/posts/<slug>/chart.png' | relative_url }}`. Keep images small (PNG or WebP, under ~300 KB).
- **Code:** short snippets go in fenced blocks with a language. Anything a reader needs to run belongs in a public repo or gist, linked from the post, with exact versions.
- **Liquid:** a code block that contains `{{` or `{%` must be wrapped in `{% raw %}` … `{% endraw %}`, or the build fails.

## What a good post here looks like

Posts are about **something the user built, or something they found out**. A reader should be able to trust the claims and redo the work.

- **Open with the result**, in a sentence or two: what, how much, on what hardware.
- **Then the story in order:** the problem, how it was measured, what was tried (including what didn't work and why), and what finally worked.
- **Numbers with their conditions:** machine, versions, input, and how each was measured. Use a table when comparing.
- **How to do it yourself:** exact steps or commands, and the repo or gist link.
- **Limits and caveats:** where it wasn't tested and what could break.
- **Sources:** link everything the post leans on.
- **Voice:** plain and first person (the user's voice, not Claude's). No hype words, no filler intro. Titles say what happened, not "Some thoughts on…".

Material for the post usually comes from the conversation and the project. Use the real measured numbers; never invent or round them in a way that changes the claim.

## Editing a published post

Edit the file under `_posts/`, keeping its name so the URL stays the same. For a change in substance, add a line at the end: `*Updated D Month YYYY: what changed.*`. Then follow the same publish and verify steps. Deleting a post also needs the user's say-so.

## The design (keep it consistent)
The site is an **engineering computation pad**: pale green paper with a faint grid, a margin rule, graphite ink, drafting-blue ink for results and links, Archivo (expanded) for lettering and Newsreader for reading. Each post has a title block (project, date, reading time) and a boxed answer (`result`). In a post's Markdown, use plain headings, lists, tables and fenced code; the stylesheet handles the look. Don't add inline styles, emojis as icons, or all-caps labels.

## Local preview (optional)
There's normally no need: GitHub builds the site. If `~/.local/bin/jekyll-lite` exists (a small wrapper around Jekyll that needs no `ruby-dev`):
```
cd ~/dev/blog && BASEURL=/blog PORT=4011 jekyll-lite serve --drafts    # http://127.0.0.1:4011/blog/
```
Otherwise, with Ruby and Bundler: add a `Gemfile` with `gem "github-pages", group: :jekyll_plugins` (keep it out of the commit), then `bundle install && bundle exec jekyll serve --drafts` and open `http://127.0.0.1:4000/blog/`.
