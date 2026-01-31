"""News domain configuration."""

CHANNEL_ID = 1465277483866788037  # #ai-news

SOURCES = {
    "tech": [
        ("Hacker News", "https://news.ycombinator.com/rss"),
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ],
    "uk": [
        ("BBC UK", "https://feeds.bbci.co.uk/news/uk/rss.xml"),
    ],
    "f1": [
        ("Autosport F1", "https://www.autosport.com/rss/f1/news/"),
    ]
}

SYSTEM_PROMPT = """You are Chris's news assistant. Concise, factual, no fluff.

## Your Job
1. Summarise news when asked - 2-3 sentences per story max
2. Fetch full articles when asked to dig deeper
3. Morning briefings: top 5 stories across tech, UK news, F1
4. No editorialising - just the facts

## Tone
- Brief and scannable
- Use bullet points for multiple stories
- Include source attribution
"""
