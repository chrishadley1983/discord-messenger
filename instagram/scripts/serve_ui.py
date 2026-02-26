"""
Instagram Saved Posts Browser

Single-file FastAPI app serving a browsable UI for downloaded Instagram posts.
Loads master_index.json + per-post analysis/caption/transcript on startup.

Usage:
    python scripts/serve_ui.py
    → http://localhost:8080
"""

import json
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
INDEX_FILE = ROOT / "data" / "master_index.json"

app = FastAPI()

# ---------------------------------------------------------------------------
# Data loading (runs once at startup)
# ---------------------------------------------------------------------------
POSTS: list[dict] = []
COLLECTIONS: list[str] = []


def _read_text(p: Path) -> str | None:
    if p.exists():
        return p.read_text(encoding="utf-8", errors="replace").strip()
    return None


def _read_json(p: Path) -> dict | None:
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return None
    return None


def _find_thumbnail(post_dir: Path, shortcode: str) -> str | None:
    """Return relative media path for the best thumbnail."""
    frames = post_dir / "frames"
    if frames.exists() and (frames / "frame_001.jpg").exists():
        return f"frames/frame_001.jpg"
    # photo post: {shortcode}.jpg or {shortcode}_1.jpg
    if (post_dir / f"{shortcode}.jpg").exists():
        return f"{shortcode}.jpg"
    if (post_dir / f"{shortcode}_1.jpg").exists():
        return f"{shortcode}_1.jpg"
    return None


def _find_video(post_dir: Path, shortcode: str) -> str | None:
    mp4 = post_dir / f"{shortcode}.mp4"
    return f"{shortcode}.mp4" if mp4.exists() else None


def _find_photos(post_dir: Path, shortcode: str) -> list[str]:
    """Find all carousel/photo images (not frames)."""
    photos = []
    # Single photo
    single = post_dir / f"{shortcode}.jpg"
    if single.exists():
        photos.append(f"{shortcode}.jpg")
    # Carousel: {shortcode}_1.jpg, _2.jpg, ...
    i = 1
    while True:
        p = post_dir / f"{shortcode}_{i}.jpg"
        if p.exists():
            photos.append(f"{shortcode}_{i}.jpg")
            i += 1
        else:
            break
    return photos


def _find_frames(post_dir: Path) -> list[str]:
    frames_dir = post_dir / "frames"
    if not frames_dir.exists():
        return []
    return sorted(
        f"frames/{f.name}" for f in frames_dir.iterdir()
        if f.suffix == ".jpg"
    )


def load_data():
    global POSTS, COLLECTIONS

    index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    COLLECTIONS = list(index["collections"].keys())

    for entry in index["posts"]:
        sc = entry["shortcode"]
        post_dir = DOWNLOADS / sc

        if not post_dir.exists():
            continue

        analysis = _read_json(post_dir / "analysis.json")
        meta = _read_json(post_dir / "meta.json")
        caption = _read_text(post_dir / "caption.txt")
        transcript = _read_text(post_dir / "transcript.txt")

        # Determine title from analysis
        title = None
        if analysis:
            title = (
                analysis.get("one_line_summary")
                or analysis.get("dish_name")
                or analysis.get("exercise_name")
                or analysis.get("title")
            )
        if not title and caption:
            title = caption[:80] + ("..." if len(caption) > 80 else "")
        if not title:
            title = sc

        collections = entry.get("collections", [])
        # Determine display collection
        if collections:
            collection = collections[0]
        elif analysis and analysis.get("best_guess_collection"):
            collection = analysis["best_guess_collection"]
        else:
            collection = "Uncollected"

        post = {
            "shortcode": sc,
            "url": entry.get("url", f"https://www.instagram.com/p/{sc}/"),
            "username": entry.get("username", meta.get("owner_username", "") if meta else ""),
            "title": title,
            "collection": collection,
            "collections": collections,
            "media_type": entry.get("media_type", "post"),
            "caption": caption,
            "transcript": transcript,
            "analysis": analysis,
            "thumbnail": _find_thumbnail(post_dir, sc),
            "video": _find_video(post_dir, sc),
            "photos": _find_photos(post_dir, sc),
            "frames": _find_frames(post_dir),
            "likes": meta.get("likes") if meta else None,
            "date": meta.get("date_utc") if meta else None,
        }
        POSTS.append(post)

    print(f"Loaded {len(POSTS)} posts across collections: {COLLECTIONS}")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
@app.get("/api/posts")
def api_posts():
    return JSONResponse(POSTS)


@app.get("/media/{shortcode}/{path:path}")
def serve_media(shortcode: str, path: str):
    file_path = DOWNLOADS / shortcode / path
    if not file_path.exists() or not file_path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(file_path)


@app.get("/")
def index():
    return HTMLResponse(HTML_PAGE)


# ---------------------------------------------------------------------------
# Embedded HTML/CSS/JS
# ---------------------------------------------------------------------------
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Instagram Saved Posts</title>
<style>
:root {
  --bg: #fafafa;
  --card-bg: #fff;
  --text: #262626;
  --text-secondary: #8e8e8e;
  --border: #dbdbdb;
  --accent: #0095f6;
  --pill-bg: #efefef;
  --pill-active: #262626;
  --pill-active-text: #fff;
  --modal-bg: rgba(0,0,0,0.65);
  --shadow: 0 1px 3px rgba(0,0,0,0.12);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
}

/* Header */
.header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--card-bg);
  border-bottom: 1px solid var(--border);
  padding: 16px 24px;
}

.header h1 {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 12px;
}

.header-stats {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.search-bar {
  width: 100%;
  max-width: 480px;
  padding: 10px 16px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  background: var(--bg);
  margin-bottom: 12px;
}

.search-bar:focus {
  border-color: var(--accent);
}

/* Filter pills */
.pills {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pill {
  padding: 6px 16px;
  border-radius: 20px;
  border: 1px solid var(--border);
  background: var(--pill-bg);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s;
  user-select: none;
}

.pill:hover { border-color: var(--text-secondary); }

.pill.active {
  background: var(--pill-active);
  color: var(--pill-active-text);
  border-color: var(--pill-active);
}

.pill .count {
  font-weight: 400;
  opacity: 0.7;
  margin-left: 4px;
}

/* Grid */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

/* Cards */
.card {
  background: var(--card-bg);
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border);
  cursor: pointer;
  transition: box-shadow 0.2s, transform 0.15s;
}

.card:hover {
  box-shadow: var(--shadow);
  transform: translateY(-2px);
}

.card-thumb {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  display: block;
  background: #efefef;
}

.card-body {
  padding: 12px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.3;
  margin-bottom: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  font-size: 12px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  background: var(--pill-bg);
}

.badge-travel { background: #e3f2fd; color: #1565c0; }
.badge-recipes { background: #fce4ec; color: #c62828; }
.badge-stretching { background: #e8f5e9; color: #2e7d32; }
.badge-life-hacks { background: #fff3e0; color: #e65100; }
.badge-uncollected { background: #f3e5f5; color: #6a1b9a; }

.card-type {
  font-size: 11px;
  color: var(--text-secondary);
}

/* No results */
.no-results {
  grid-column: 1 / -1;
  text-align: center;
  padding: 60px 20px;
  color: var(--text-secondary);
  font-size: 16px;
}

/* Modal */
.modal-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: var(--modal-bg);
  z-index: 1000;
  justify-content: center;
  align-items: flex-start;
  padding: 40px 20px;
  overflow-y: auto;
}

.modal-overlay.open {
  display: flex;
}

.modal {
  background: var(--card-bg);
  border-radius: 12px;
  max-width: 800px;
  width: 100%;
  max-height: none;
  overflow: visible;
  position: relative;
}

.modal-close {
  position: absolute;
  top: -36px;
  right: 0;
  background: none;
  border: none;
  color: #fff;
  font-size: 28px;
  cursor: pointer;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-media {
  width: 100%;
  background: #000;
  border-radius: 12px 12px 0 0;
  position: relative;
}

.modal-media video {
  width: 100%;
  max-height: 500px;
  display: block;
}

.modal-media img.main-photo {
  width: 100%;
  max-height: 500px;
  object-fit: contain;
  display: block;
  margin: 0 auto;
}

/* Frames gallery */
.frames-gallery {
  display: flex;
  gap: 4px;
  overflow-x: auto;
  padding: 8px 16px;
  background: #000;
}

.frames-gallery img {
  height: 64px;
  width: auto;
  border-radius: 4px;
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 0.15s;
  flex-shrink: 0;
}

.frames-gallery img:hover { opacity: 1; }
.frames-gallery img.active { opacity: 1; border: 2px solid var(--accent); }

/* Photo carousel */
.carousel {
  position: relative;
}

.carousel-photos {
  display: flex;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
}

.carousel-photos img {
  width: 100%;
  flex-shrink: 0;
  scroll-snap-align: start;
  object-fit: contain;
  max-height: 500px;
  background: #000;
}

.carousel-dots {
  display: flex;
  justify-content: center;
  gap: 6px;
  padding: 8px;
  background: #000;
}

.carousel-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(255,255,255,0.4);
}

.carousel-dot.active {
  background: #fff;
}

/* Modal body */
.modal-body {
  padding: 20px;
}

.modal-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 4px;
}

.modal-username {
  color: var(--accent);
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 12px;
}

.modal-username a {
  color: inherit;
  text-decoration: none;
}

.modal-username a:hover {
  text-decoration: underline;
}

.modal-section {
  margin-bottom: 16px;
}

.modal-section h3 {
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.modal-section p,
.modal-section ul {
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.modal-section ul {
  padding-left: 20px;
}

.modal-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.modal-tag {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  background: var(--pill-bg);
  font-weight: 500;
}

.modal-link {
  display: inline-block;
  margin-top: 8px;
  color: var(--accent);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
}

.modal-link:hover { text-decoration: underline; }

/* Responsive */
@media (max-width: 640px) {
  .grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    padding: 8px;
  }
  .header { padding: 12px 16px; }
  .modal { margin: 0; border-radius: 0; min-height: 100vh; }
  .modal-media { border-radius: 0; }
  .modal-overlay { padding: 0; }
  .modal-close { top: 8px; right: 8px; color: #fff; z-index: 10; }
}
</style>
</head>
<body>

<div class="header">
  <h1>Instagram Saved Posts</h1>
  <div class="header-stats" id="stats"></div>
  <input type="text" class="search-bar" id="search" placeholder="Search posts..." />
  <div class="pills" id="pills"></div>
</div>

<div class="grid" id="grid"></div>

<div class="modal-overlay" id="modal-overlay">
  <div class="modal" id="modal">
    <button class="modal-close" id="modal-close">&times;</button>
    <div class="modal-media" id="modal-media"></div>
    <div class="modal-body" id="modal-body"></div>
  </div>
</div>

<script>
let allPosts = [];
let activeCollection = 'All';
let searchQuery = '';
let debounceTimer = null;

// Badge class map
const badgeClass = {
  'Travel': 'badge-travel',
  'Recipes': 'badge-recipes',
  'Stretching': 'badge-stretching',
  'Life Hacks etc': 'badge-life-hacks',
  'Life Hacks': 'badge-life-hacks',
  'Uncollected': 'badge-uncollected',
};

async function init() {
  const resp = await fetch('/api/posts');
  allPosts = await resp.json();

  buildPills();
  updateStats();
  render();
}

function buildPills() {
  const counts = { 'All': allPosts.length };
  for (const p of allPosts) {
    const c = p.collection;
    counts[c] = (counts[c] || 0) + 1;
  }

  const pillsEl = document.getElementById('pills');
  const names = ['All', ...Object.keys(counts).filter(k => k !== 'All').sort()];

  for (const name of names) {
    const el = document.createElement('span');
    el.className = 'pill' + (name === 'All' ? ' active' : '');
    el.innerHTML = `${esc(name)}<span class="count">${counts[name] || 0}</span>`;
    el.onclick = () => {
      document.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
      el.classList.add('active');
      activeCollection = name;
      render();
    };
    pillsEl.appendChild(el);
  }
}

function updateStats() {
  const filtered = getFiltered();
  document.getElementById('stats').textContent =
    `Showing ${filtered.length} of ${allPosts.length} posts`;
}

function getFiltered() {
  let posts = allPosts;

  if (activeCollection !== 'All') {
    posts = posts.filter(p => p.collection === activeCollection);
  }

  if (searchQuery) {
    const q = searchQuery.toLowerCase();
    posts = posts.filter(p => {
      const fields = [
        p.title, p.username, p.caption, p.transcript,
        p.collection,
        p.analysis ? JSON.stringify(p.analysis) : ''
      ];
      return fields.some(f => f && f.toLowerCase().includes(q));
    });
  }

  return posts;
}

function render() {
  const posts = getFiltered();
  updateStats();

  const grid = document.getElementById('grid');
  grid.innerHTML = '';

  if (posts.length === 0) {
    grid.innerHTML = '<div class="no-results">No posts match your search.</div>';
    return;
  }

  for (const post of posts) {
    const card = document.createElement('div');
    card.className = 'card';

    const thumbUrl = post.thumbnail
      ? `/media/${post.shortcode}/${post.thumbnail}`
      : '';

    const bc = badgeClass[post.collection] || 'badge-uncollected';

    card.innerHTML = `
      ${thumbUrl ? `<img class="card-thumb" src="${thumbUrl}" loading="lazy" alt="" />` :
        '<div class="card-thumb" style="display:flex;align-items:center;justify-content:center;color:#ccc;font-size:48px;">&#128247;</div>'}
      <div class="card-body">
        <div class="card-title">${esc(post.title)}</div>
        <div class="card-meta">
          <span>@${esc(post.username)}</span>
          <span class="card-badge ${bc}">${esc(post.collection)}</span>
          ${post.video ? '<span class="card-type">&#9654; Video</span>' : ''}
        </div>
      </div>
    `;

    card.onclick = () => openModal(post);
    grid.appendChild(card);
  }
}

function openModal(post) {
  const overlay = document.getElementById('modal-overlay');
  const mediaEl = document.getElementById('modal-media');
  const bodyEl = document.getElementById('modal-body');

  // Media section
  let mediaHtml = '';

  if (post.video) {
    mediaHtml += `<video controls preload="metadata" poster="${post.thumbnail ? `/media/${post.shortcode}/${post.thumbnail}` : ''}">
      <source src="/media/${post.shortcode}/${post.video}" type="video/mp4">
    </video>`;
  } else if (post.photos.length > 1) {
    // Carousel
    mediaHtml += '<div class="carousel"><div class="carousel-photos">';
    for (const photo of post.photos) {
      mediaHtml += `<img src="/media/${post.shortcode}/${photo}" alt="" />`;
    }
    mediaHtml += '</div>';
    if (post.photos.length > 1) {
      mediaHtml += '<div class="carousel-dots">';
      for (let i = 0; i < post.photos.length; i++) {
        mediaHtml += `<div class="carousel-dot${i === 0 ? ' active' : ''}"></div>`;
      }
      mediaHtml += '</div>';
    }
    mediaHtml += '</div>';
  } else if (post.photos.length === 1) {
    mediaHtml += `<img class="main-photo" src="/media/${post.shortcode}/${post.photos[0]}" alt="" />`;
  } else if (post.thumbnail) {
    mediaHtml += `<img class="main-photo" src="/media/${post.shortcode}/${post.thumbnail}" alt="" />`;
  }

  // Frames gallery (for video posts)
  if (post.video && post.frames.length > 1) {
    mediaHtml += '<div class="frames-gallery">';
    for (const frame of post.frames) {
      mediaHtml += `<img src="/media/${post.shortcode}/${frame}" alt="" />`;
    }
    mediaHtml += '</div>';
  }

  mediaEl.innerHTML = mediaHtml;

  // Wire up carousel scroll
  const carouselPhotos = mediaEl.querySelector('.carousel-photos');
  if (carouselPhotos) {
    const dots = mediaEl.querySelectorAll('.carousel-dot');
    carouselPhotos.addEventListener('scroll', () => {
      const idx = Math.round(carouselPhotos.scrollLeft / carouselPhotos.offsetWidth);
      dots.forEach((d, i) => d.classList.toggle('active', i === idx));
    });
  }

  // Body section
  let bodyHtml = '';

  const bc = badgeClass[post.collection] || 'badge-uncollected';
  bodyHtml += `<div class="modal-title">${esc(post.title)}</div>`;
  bodyHtml += `<div class="modal-username">
    <a href="https://www.instagram.com/${post.username}/" target="_blank">@${esc(post.username)}</a>
    &nbsp; <span class="card-badge ${bc}">${esc(post.collection)}</span>
    ${post.date ? ` &nbsp; <span style="color:var(--text-secondary);font-size:12px">${new Date(post.date).toLocaleDateString()}</span>` : ''}
    ${post.likes ? ` &nbsp; <span style="color:var(--text-secondary);font-size:12px">&#10084; ${post.likes.toLocaleString()}</span>` : ''}
  </div>`;

  // Analysis fields (collection-specific)
  if (post.analysis) {
    const a = post.analysis;
    bodyHtml += '<div class="modal-section"><h3>Analysis</h3><div class="modal-tags">';

    if (a.country) bodyHtml += `<span class="modal-tag">${esc(a.country)}</span>`;
    if (a.city_or_region) bodyHtml += `<span class="modal-tag">${esc(a.city_or_region)}</span>`;
    if (a.category) bodyHtml += `<span class="modal-tag">${esc(a.category.replace(/_/g, ' '))}</span>`;
    if (a.best_time_to_visit) bodyHtml += `<span class="modal-tag">Best: ${esc(a.best_time_to_visit)}</span>`;
    if (a.estimated_cost_level) bodyHtml += `<span class="modal-tag">Cost: ${esc(a.estimated_cost_level)}</span>`;
    if (a.cuisine_type) bodyHtml += `<span class="modal-tag">${esc(a.cuisine_type)}</span>`;
    if (a.meal_type) bodyHtml += `<span class="modal-tag">${esc(a.meal_type)}</span>`;
    if (a.difficulty) bodyHtml += `<span class="modal-tag">${esc(a.difficulty)}</span>`;
    if (a.body_area) bodyHtml += `<span class="modal-tag">${esc(a.body_area)}</span>`;
    if (a.duration_or_reps) bodyHtml += `<span class="modal-tag">${esc(a.duration_or_reps)}</span>`;
    if (a.equipment_needed) bodyHtml += `<span class="modal-tag">Equipment: ${esc(a.equipment_needed)}</span>`;
    if (a.confidence) bodyHtml += `<span class="modal-tag">Confidence: ${esc(a.confidence)}</span>`;

    bodyHtml += '</div>';

    // Dish name / one-line summary if different from title
    if (a.dish_name && a.dish_name !== post.title) {
      bodyHtml += `<p style="margin-top:8px">${esc(a.dish_name)}</p>`;
    }
    if (a.one_line_summary && a.one_line_summary !== post.title) {
      bodyHtml += `<p style="margin-top:8px">${esc(a.one_line_summary)}</p>`;
    }

    // Ingredients
    if (a.ingredients_visible && a.ingredients_visible.length > 0) {
      bodyHtml += '<div class="modal-section"><h3>Ingredients</h3><ul>';
      for (const ing of a.ingredients_visible) {
        bodyHtml += `<li>${esc(ing)}</li>`;
      }
      bodyHtml += '</ul></div>';
    }

    // Method
    if (a.method_summary) {
      bodyHtml += `<div class="modal-section"><h3>Method</h3><p>${esc(a.method_summary)}</p></div>`;
    }

    // Instructions
    if (a.instructions_summary) {
      bodyHtml += `<div class="modal-section"><h3>Instructions</h3><p>${esc(a.instructions_summary)}</p></div>`;
    }

    // Notes
    if (a.notes) {
      bodyHtml += `<div class="modal-section"><h3>Notes</h3><p>${esc(a.notes)}</p></div>`;
    }

    bodyHtml += '</div>';
  }

  // Caption
  if (post.caption) {
    const captionDisplay = post.caption.length > 500
      ? post.caption.slice(0, 500) + '...'
      : post.caption;
    bodyHtml += `<div class="modal-section"><h3>Caption</h3><p>${esc(captionDisplay)}</p></div>`;
  }

  // Transcript
  if (post.transcript) {
    const transcriptDisplay = post.transcript.length > 500
      ? post.transcript.slice(0, 500) + '...'
      : post.transcript;
    bodyHtml += `<div class="modal-section"><h3>Transcript</h3><p>${esc(transcriptDisplay)}</p></div>`;
  }

  // Instagram link
  bodyHtml += `<a class="modal-link" href="${post.url}" target="_blank">View on Instagram &rarr;</a>`;

  bodyEl.innerHTML = bodyHtml;

  overlay.classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  const overlay = document.getElementById('modal-overlay');
  overlay.classList.remove('open');
  document.body.style.overflow = '';
  // Stop any playing videos
  const video = overlay.querySelector('video');
  if (video) video.pause();
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

// Event listeners
document.getElementById('search').addEventListener('input', (e) => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    searchQuery = e.target.value.trim();
    render();
  }, 250);
});

document.getElementById('modal-close').addEventListener('click', closeModal);
document.getElementById('modal-overlay').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closeModal();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeModal();
});

init();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    load_data()
    uvicorn.run(app, host="0.0.0.0", port=8080)
else:
    load_data()
