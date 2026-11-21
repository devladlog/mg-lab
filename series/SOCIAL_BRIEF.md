# Social post drafts — brief

Every category-series episode gets a `social.yaml` next to its `script.yaml`. These are **drafts held for the owner's review**: nothing is scheduled or posted, no Metricool, no sign-ins, no browser.

## Sources (and only these)
Write each post from that episode's own `script.yaml`, `README.md` and `demo.md`. Every claim in a post must be something the episode really shows or says. No invented numbers, results, prices or features. If a fact in the episode is marked "not verified" or "needs tenant", leave it out of the posts.

## Confidentiality
No client names. No real tenant names, domains, URLs, user names or ids. Use the episode's fictional Contoso / Fabrikam names only. Links stay as placeholders: `{YOUTUBE_URL}`, `{SHORT_URL}`, `{REPO_URL}` (the public GitHub repo for the episode code), `{BLOG_URL}` (only if the script's `sources:` has a devladlog.com guide).

## Voice
English. Plain, practical, engineer-to-engineer. No hype words ("game-changer", "revolutionary", "unlock", "supercharge", "dive in"), no emoji walls (at most 2 emoji per post, none on LinkedIn company). Lead with the concrete problem or the surprising finding (the episode's gotcha is usually the best hook). Brand: channel "DEVLADLOG", company "Momento Galático".

## AI disclosure
The videos use a synthetic (TTS) voice. Every post sets `ai_label: true` (the owner switches on each platform's AI-generated content label when scheduling) and the YouTube/Facebook/LinkedIn texts end with the line: `Narration uses an AI voice.`

## File format (`social.yaml`)
```yaml
episode: 15
series: "DEVLADLOG AI"
status: draft-hold-for-review
ai_label: true
youtube_url: "{YOUTUBE_URL}"
linkedin_company:        # Momento Galático page. 120-220 words. Hook line, 2-4 short lines or bullets on what is built/shown, CTA with {YOUTUBE_URL}, then 3-5 hashtags on the last line.
  text: |
    ...
linkedin_personal:       # Owner's profile, first person, 60-140 words, conversational, one concrete lesson, {YOUTUBE_URL}, max 3 hashtags.
  text: |
    ...
facebook:                # 50-110 words, friendly, {YOUTUBE_URL}, max 3 hashtags.
  text: |
    ...
shorts:                  # one entry per scene with `short:` in script.yaml, same ids, same order
  - id: hook
    youtube_short_title: "..."   # <= 90 characters, ends with #Shorts
    instagram_reel:              # caption 40-120 words, "Full episode: link in bio", max 5 hashtags
      caption: |
        ...
      cover_text: "..."          # <= 32 characters, for the reel cover
    tiktok:                      # caption <= 300 characters including hashtags, max 5 hashtags
      caption: "..."
```

## Hashtags
Specific beats generic: e.g. `#PowerApps #Dataverse #PowerFx` over `#Tech #Coding`. Always include one series-level tag from: `#Azure #PowerPlatform #Microsoft365 #SharePoint #PowerBI #DotNet #SQLServer #WindowsServer #Dynamics365 #AzureAI #GitHubCopilot #MicrosoftCopilot #DevTools`. Never use more than the per-platform maximum above.

## Check
Run `python3 /home/claude/mglab/mg-lab/series/tools/check_social.py <episode folders...>` and fix every error before handing back.
