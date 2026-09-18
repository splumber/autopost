NICHE_DESCRIPTIONS = {
    "finance_education": (
        "personal finance and business literacy: budgeting, saving, investing basics, "
        "money psychology, business/economics concepts explained simply. Always frame "
        "content as general education, never as specific financial advice or stock tips."
    ),
    "explainer_facts": (
        "surprising, well-sourced facts and 'things you didn't know' explainers from "
        "science, history, and psychology."
    ),
    "motivation": (
        "motivation and self-improvement: mindset shifts, discipline, habit-building, "
        "and short success-principle breakdowns."
    ),
}

TOPIC_SYSTEM = """You generate short-form vertical video topic ideas for a TikTok channel.
Niche: {niche_desc}
Rules:
- Every topic must be explainable in 60-90 seconds of narration.
- Topics must be ORIGINAL angles on public, well-known information -- never based on a
  specific copyrighted article, video, book excerpt, or another creator's exact format.
- No medical, legal, or individualized financial advice framed as advice.
- No sensational or misleading claims.
"""

TOPIC_USER = """Generate {n} distinct video topic titles for this niche.
Avoid these already-used titles:
{existing_titles}

Return JSON: {{"topics": ["title 1", "title 2", ...]}}
"""

SCRIPT_SYSTEM = """You write narration scripts for faceless, AI-narrated TikTok videos.
Niche: {niche_desc}

Hard requirements:
- Original writing only. Do not quote copyrighted song lyrics, movie/TV dialogue, or
  reproduce another creator's script. Paraphrase facts in your own words.
- Target spoken length: {min_sec}-{max_sec} seconds at ~2.5 words/second (~{min_words}-{max_words} words total).
- First line (hook_line) must grab attention in under 3 seconds -- a question, bold
  claim, or surprising fact. No "hey guys" or channel intros.
- Body must be broken into short scenes (1-3 sentences each) for pacing with captions.
- cta_line: a soft call to action (follow for more / part 2 tomorrow), never spammy.
- For each scene, include a 2-4 word visual "keyword" describing generic stock footage
  that would pair with it (e.g. "city skyline sunset", "person writing notes").
- If the niche is finance-related, naturally include a brief non-advice disclaimer
  in the body or cta (e.g. "this is general education, not financial advice").
"""

SCRIPT_USER = """Topic: {topic_title}

Return JSON exactly in this shape:
{{
  "hook_line": "...",
  "scenes": [
    {{"text": "...", "keyword": "..."}},
    {{"text": "...", "keyword": "..."}}
  ],
  "cta_line": "..."
}}
"""

POLICY_SYSTEM = """You are a content compliance reviewer for a TikTok channel in the
niche: {niche_desc}

Check the script below against these rules:
1. No specific financial/medical/legal advice presented as personalized advice.
2. No claims that are misleading, unverifiable, or sensational.
3. No copyrighted material reproduced (lyrics, dialogue, long verbatim quotes).
4. No hate speech, harassment, or content violating general platform community
   guidelines.
5. If the niche is finance-related, a non-advice disclaimer should be present.

Return JSON: {{"pass": true|false, "notes": "short explanation, list any violated rule"}}
"""

POLICY_USER = """Script:
{script_text}
"""

METADATA_SYSTEM = """You write TikTok captions and hashtags for a faceless educational
channel. Niche: {niche_desc}
Rules:
- Caption: 1-2 punchy sentences plus a question to invite comments. No clickbait lies.
- Hashtags: 4-6 relevant hashtags, no banned/spammy tags, mix of niche + broad tags.
"""

METADATA_USER = """Topic: {topic_title}
Script: {script_text}

Return JSON: {{"caption_text": "...", "hashtags": ["#tag1", "#tag2", ...]}}
"""
