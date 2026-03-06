"""Airbnb booking scraper.

Finds Airbnb reservation confirmation emails, extracts listing links,
and scrapes property details via Playwright (Airbnb is JS-rendered).

Primary extraction uses the __NEXT_DATA__ JSON blob embedded in the page,
which contains the full listing data. Falls back to DOM-based extraction
if the JSON approach fails.
"""

import json
import re
from datetime import datetime
from typing import Any, Optional

from logger import logger
from .base import BaseEmailLinkScraper, ScrapedItem


# Match Airbnb listing URLs (rooms/12345)
LISTING_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?airbnb\.(?:co\.uk|com)/rooms/(\d+)"
)


def _recursive_find(obj: Any, target_keys: set[str], max_depth: int = 15) -> dict[str, Any]:
    """Recursively search a nested dict/list for specific keys.

    Returns a dict mapping found key -> value (first match wins).
    """
    results: dict[str, Any] = {}
    if max_depth <= 0 or len(results) >= len(target_keys):
        return results
    _recursive_find_inner(obj, target_keys, max_depth, results)
    return results


def _recursive_find_inner(obj: Any, target_keys: set[str], depth: int, results: dict[str, Any]):
    """Inner recursive helper."""
    if depth <= 0:
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in target_keys and key not in results:
                results[key] = value
            if len(results) >= len(target_keys):
                return
            _recursive_find_inner(value, target_keys, depth - 1, results)
            if len(results) >= len(target_keys):
                return
    elif isinstance(obj, list):
        for item in obj:
            _recursive_find_inner(item, target_keys, depth - 1, results)
            if len(results) >= len(target_keys):
                return


def _find_all_values(obj: Any, target_key: str, max_depth: int = 15) -> list[Any]:
    """Find ALL values for a given key at any depth."""
    results: list[Any] = []
    _find_all_inner(obj, target_key, max_depth, results)
    return results


def _find_all_inner(obj: Any, target_key: str, depth: int, results: list[Any]):
    if depth <= 0:
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == target_key:
                results.append(value)
            _find_all_inner(value, target_key, depth - 1, results)
    elif isinstance(obj, list):
        for item in obj:
            _find_all_inner(item, target_key, depth - 1, results)


class AirbnbBookingScraper(BaseEmailLinkScraper):
    """Scrape Airbnb listing pages from booking confirmation emails."""

    name = "airbnb"
    gmail_query = 'from:airbnb subject:(reservation OR "booking confirmed" OR "reservation confirmed")'
    default_topics = ["travel", "accommodation", "airbnb"]
    needs_playwright = True

    def extract_links(self, email_html: str) -> list[str]:
        """Extract Airbnb listing URLs from email body."""
        matches = LISTING_URL_PATTERN.findall(email_html)
        seen = set()
        urls = []
        for listing_id in matches:
            if listing_id not in seen:
                seen.add(listing_id)
                urls.append(f"https://www.airbnb.co.uk/rooms/{listing_id}")
        return urls

    def _make_dedup_key(self, url: str, order_date: Optional[datetime]) -> str:
        """Build dedup key: listing URL + booking month.

        Same property on different trips = separate items.
        """
        date_suffix = order_date.strftime("-%Y-%m") if order_date else ""
        return f"{url}{date_suffix}"

    async def scrape_link(self, page, url: str) -> Optional[ScrapedItem]:
        """Scrape an Airbnb listing page via Playwright.

        Strategy:
        1. Try __NEXT_DATA__ JSON extraction (richest data)
        2. Try window.__NEXT_DATA__ via JS evaluation
        3. Fall back to DOM-based extraction
        4. Then fetch review highlights by clicking "Show all reviews"
        """
        try:
            await page.goto(url, wait_until="networkidle", timeout=45000)
            await page.wait_for_selector("h1", timeout=15000)

            # Extract title from DOM (always reliable)
            title = await page.text_content("h1") or "Airbnb Listing"
            title = title.strip()

            # Try JSON-based extraction first
            listing_data = await self._extract_next_data(page)

            if listing_data:
                logger.info(f"Airbnb: extracted __NEXT_DATA__ for {url}")
                item = self._build_item_from_json(title, url, listing_data)
            else:
                # Fallback: try getting dehydrated state or API data from page scripts
                listing_data = await self._extract_dehydrated_state(page)
                if listing_data:
                    logger.info(f"Airbnb: extracted dehydrated state for {url}")
                    item = self._build_item_from_json(title, url, listing_data)
                else:
                    # Final fallback: DOM-based extraction
                    logger.info(f"Airbnb: falling back to DOM extraction for {url}")
                    item = await self._scrape_from_dom(page, title, url)

            if not item:
                return None

            # Fetch review highlights (reviews are lazy-loaded via API)
            review_highlights = await self._fetch_review_highlights(page)
            if review_highlights:
                item.content += "\n\n## Guest Review Highlights\n"
                for highlight in review_highlights:
                    item.content += f"- {highlight}\n"
                logger.info(f"Airbnb: added {len(review_highlights)} review highlights for {url}")

            return item

        except Exception as e:
            logger.warning(f"Failed to scrape Airbnb listing {url}: {e}")
            return None

    async def _fetch_review_highlights(self, page) -> list[str]:
        """Click 'Show all reviews' and extract practical highlights from review text.

        Reviews are lazy-loaded via API when the reviews modal opens.
        We intercept the API response to get the raw review comments,
        then use Claude to extract practical insights.
        """
        review_comments: list[str] = []

        async def capture_review_response(response):
            """Intercept API responses containing review data."""
            try:
                ct = response.headers.get("content-type", "")
                if "json" in ct and response.status == 200:
                    body = await response.text()
                    if len(body) > 500 and "comment" in body.lower():
                        data = json.loads(body)
                        self._extract_comments_from_response(data, review_comments)
            except Exception:
                pass

        page.on("response", capture_review_response)

        try:
            # Click "Show all N reviews" button via JS to avoid modal overlay issues
            clicked = await page.evaluate("""() => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    const text = btn.textContent || '';
                    if (text.includes('Show all') && text.includes('review')) {
                        btn.scrollIntoView();
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")

            if not clicked:
                logger.debug("Airbnb: no 'Show all reviews' button found")
                return []

            # Wait for the API response with review data
            await page.wait_for_timeout(4000)

            # Close the modal
            try:
                await page.evaluate("""() => {
                    const close = document.querySelector('[role="dialog"] button[aria-label="Close"]');
                    if (close) close.click();
                }""")
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"Airbnb: review fetch failed: {e}")
        finally:
            page.remove_listener("response", capture_review_response)

        if not review_comments:
            return []

        # Deduplicate (API often returns duplicates)
        seen = set()
        unique_comments = []
        for comment in review_comments:
            clean = comment.strip()[:300]
            if clean not in seen and len(clean) > 20:
                seen.add(clean)
                unique_comments.append(clean)

        logger.info(f"Airbnb: captured {len(unique_comments)} unique review comments")

        # Use Claude to extract practical highlights
        return await self._distill_review_highlights(unique_comments)

    def _extract_comments_from_response(self, data: Any, comments: list[str]) -> None:
        """Recursively extract review comment text from API response JSON."""
        if isinstance(data, dict):
            for key, value in data.items():
                if key in ("comments", "reviewText", "comment") and isinstance(value, str) and len(value) > 20:
                    # Strip HTML tags
                    clean = re.sub(r"<[^>]+>", " ", value).strip()
                    clean = re.sub(r"\s+", " ", clean)
                    comments.append(clean)
                else:
                    self._extract_comments_from_response(value, comments)
        elif isinstance(data, list):
            for item in data[:30]:
                self._extract_comments_from_response(item, comments)

    async def _distill_review_highlights(self, comments: list[str]) -> list[str]:
        """Use Claude to extract practical insights from raw review text.

        Returns short, actionable highlights like:
        - "Parking is difficult - use the car park 2 streets away"
        - "Great coffee shop next door"
        - "Aircon only in living room, bedrooms can get hot"
        """
        if not comments:
            return []

        try:
            from config import call_claude_via_cli
        except ImportError:
            logger.warning("Airbnb: call_claude_via_cli not available for review distillation")
            # Fallback: return first 5 comments truncated
            return [c[:150] for c in comments[:5]]

        # Combine reviews for Claude (limit to ~3000 chars to keep prompt small)
        combined = "\n---\n".join(comments[:15])
        if len(combined) > 3000:
            combined = combined[:3000]

        prompt = f"""Extract 5-8 practical highlights from these Airbnb guest reviews. Focus on specific, useful observations that would help a future guest — things like:
- Transport/parking tips
- Neighbourhood recommendations (cafes, shops, restaurants)
- Property quirks (noise, temperature, space issues)
- Check-in/checkout specifics
- Cleanliness or maintenance notes
- What's genuinely great vs what to watch out for

Each highlight should be one concise sentence. No ratings or generic praise — only specific, actionable observations.

Reviews:
{combined}

Return ONLY the bullet points, one per line, starting with "- "."""

        try:
            result = await call_claude_via_cli(prompt, max_tokens=400, timeout=30)
            if not result:
                return [c[:150] for c in comments[:5]]

            # Parse bullet points
            highlights = []
            for line in result.strip().split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    highlights.append(line[2:].strip())
                elif line.startswith("* "):
                    highlights.append(line[2:].strip())

            return highlights[:8] if highlights else [c[:150] for c in comments[:5]]

        except Exception as e:
            logger.error(f"Airbnb: Claude review distillation failed: {e}")
            return [c[:150] for c in comments[:5]]

    async def _extract_next_data(self, page) -> Optional[dict]:
        """Extract __NEXT_DATA__ JSON from script tag or JS context."""
        # Method 1: script tag
        try:
            el = await page.query_selector("script#__NEXT_DATA__")
            if el:
                raw = await el.text_content()
                if raw:
                    data = json.loads(raw)
                    return data
        except Exception as e:
            logger.debug(f"Airbnb: script tag extraction failed: {e}")

        # Method 2: JS evaluation
        try:
            raw = await page.evaluate("JSON.stringify(window.__NEXT_DATA__)")
            if raw and raw != "undefined" and raw != "null":
                data = json.loads(raw)
                return data
        except Exception as e:
            logger.debug(f"Airbnb: JS evaluation failed: {e}")

        return None

    async def _extract_dehydrated_state(self, page) -> Optional[dict]:
        """Try to find embedded JSON data from Airbnb's dehydrated state.

        Airbnb sometimes uses a different pattern with inline script data
        or dehydrated Apollo/Relay state.
        """
        try:
            # Look for large inline script blocks with listing data
            scripts = await page.query_selector_all("script[type='application/json']")
            best_data = None
            best_size = 0
            for script in scripts:
                raw = await script.text_content()
                if raw and len(raw) > 500:
                    try:
                        data = json.loads(raw)
                        if len(raw) > best_size:
                            best_data = data
                            best_size = len(raw)
                    except json.JSONDecodeError:
                        continue
            if best_data:
                return best_data
        except Exception as e:
            logger.debug(f"Airbnb: dehydrated state extraction failed: {e}")

        # Try extracting from inline scripts that assign data
        try:
            all_scripts = await page.evaluate("""
                () => {
                    const scripts = document.querySelectorAll('script:not([src])');
                    const results = [];
                    for (const s of scripts) {
                        const text = s.textContent || '';
                        if (text.length > 1000 && (
                            text.includes('listing') ||
                            text.includes('amenities') ||
                            text.includes('description')
                        )) {
                            results.push(text.substring(0, 100000));
                        }
                    }
                    return results;
                }
            """)
            for script_text in (all_scripts or []):
                # Try to find JSON objects in the script text
                for match in re.finditer(r'\{["\'](?:listing|pdpSections|niobeMinimalClientData)["\'].*', script_text):
                    chunk = match.group(0)
                    # Try to parse progressively larger substrings
                    for end in range(len(chunk), 100, -1):
                        try:
                            data = json.loads(chunk[:end])
                            return data
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.debug(f"Airbnb: inline script extraction failed: {e}")

        # Try Airbnb's specific data pattern: niobeMinimalClientData
        try:
            niobe_data = await page.evaluate("""
                () => {
                    const scripts = document.querySelectorAll('script');
                    for (const s of scripts) {
                        const text = s.textContent || '';
                        const idx = text.indexOf('niobeMinimalClientData');
                        if (idx > -1) {
                            return text;
                        }
                    }
                    return null;
                }
            """)
            if niobe_data:
                # Extract JSON from the niobe data script
                match = re.search(r'(\[.*\])\s*$', niobe_data)
                if match:
                    try:
                        return json.loads(match.group(1))
                    except json.JSONDecodeError:
                        pass
                # Try finding the JSON blob within
                start = niobe_data.find('[')
                if start >= 0:
                    try:
                        return json.loads(niobe_data[start:])
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            logger.debug(f"Airbnb: niobe extraction failed: {e}")

        return None

    def _build_item_from_json(self, title: str, url: str, data: Any) -> ScrapedItem:
        """Build a ScrapedItem from extracted JSON data."""
        # Parse out all the fields we care about
        description = self._parse_description(data)
        amenities = self._parse_amenities(data)
        house_rules = self._parse_house_rules(data)
        location = self._parse_location(data)
        reviews = self._parse_reviews(data)
        host_info = self._parse_host_info(data)
        photo_count = self._parse_photo_count(data)
        property_type = self._parse_property_type(data)
        layout = self._parse_layout(data)
        neighbourhood = self._parse_neighbourhood(data)

        content = self._format_listing(
            title=title,
            url=url,
            property_type=property_type,
            location=location,
            layout=layout,
            amenities=amenities,
            house_rules=house_rules,
            description=description,
            reviews=reviews,
            host_info=host_info,
            photo_count=photo_count,
            neighbourhood=neighbourhood,
        )

        return ScrapedItem(
            title=f"Airbnb: {title}",
            content=content,
            url=url,
            topics=self.default_topics.copy(),
            metadata={
                "source": "airbnb",
                "property_type": property_type,
                "location": location,
                "layout": layout,
                "amenity_count": len(amenities),
                "photo_count": photo_count,
                "rating": reviews.get("rating", ""),
                "review_count": reviews.get("count", 0),
                "host_name": host_info.get("name", ""),
                "superhost": host_info.get("superhost", False),
            },
        )

    def _parse_description(self, data: Any) -> str:
        """Extract full property description from JSON data."""
        # Search for common description keys
        candidates = []

        # Look for description fields
        for key in ["description", "listingDescription", "aboutThisPlace"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, str) and len(val) > 30:
                    candidates.append(val)
                elif isinstance(val, dict):
                    # May contain htmlText or value
                    for sub_key in ["htmlText", "value", "text", "content"]:
                        if sub_key in val and isinstance(val[sub_key], str):
                            candidates.append(val[sub_key])

        # Also look in pdpSections / sections for description-type sections
        sections = _find_all_values(data, "sections")
        for section_list in sections:
            if isinstance(section_list, list):
                for section in section_list:
                    if isinstance(section, dict):
                        section_type = section.get("sectionComponentType", "") or section.get("__typename", "")
                        if "description" in section_type.lower() or "about" in section_type.lower():
                            body = section.get("section", {}) if isinstance(section.get("section"), dict) else {}
                            text = body.get("htmlDescription", {})
                            if isinstance(text, dict):
                                candidates.append(text.get("htmlText", ""))
                            elif isinstance(text, str):
                                candidates.append(text)

        # Search for PDP description sections
        for key in ["htmlDescription", "listingDefaultDescription"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, dict) and "htmlText" in val:
                    candidates.append(val["htmlText"])
                elif isinstance(val, str) and len(val) > 30:
                    candidates.append(val)

        # Strip HTML tags and pick the longest
        best = ""
        for c in candidates:
            if not isinstance(c, str):
                continue
            clean = re.sub(r"<[^>]+>", " ", c).strip()
            clean = re.sub(r"\s+", " ", clean)
            if len(clean) > len(best):
                best = clean

        return best[:3000]

    def _parse_amenities(self, data: Any) -> list[str]:
        """Extract amenities list from JSON data."""
        amenities = []
        seen = set()

        # Look for amenity-related keys
        for key in ["amenities", "previewAmenities", "listingAmenities", "amenityGroups"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, list):
                    for item in val:
                        name = None
                        if isinstance(item, str):
                            name = item
                        elif isinstance(item, dict):
                            name = item.get("title") or item.get("name") or item.get("text") or item.get("subtitle", "")
                            # Some have nested amenities within groups
                            group_amenities = item.get("amenities", [])
                            if isinstance(group_amenities, list):
                                for ga in group_amenities:
                                    if isinstance(ga, dict):
                                        ga_name = ga.get("title") or ga.get("name") or ga.get("text", "")
                                        if ga_name and ga_name not in seen:
                                            seen.add(ga_name)
                                            amenities.append(ga_name)
                                    elif isinstance(ga, str) and ga not in seen:
                                        seen.add(ga)
                                        amenities.append(ga)
                        if name and name not in seen and len(name) < 200:
                            seen.add(name)
                            amenities.append(name)

        # Also look for seeAllAmenitiesGroups
        for key in ["seeAllAmenitiesGroups", "amenitySections"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, list):
                    for group in val:
                        if isinstance(group, dict):
                            group_title = group.get("title", "")
                            items = group.get("amenities", []) or group.get("items", [])
                            if isinstance(items, list):
                                for item in items:
                                    if isinstance(item, dict):
                                        name = item.get("title") or item.get("name", "")
                                        if name and name not in seen:
                                            seen.add(name)
                                            amenities.append(name)

        return amenities[:60]  # Cap at 60

    def _parse_house_rules(self, data: Any) -> list[str]:
        """Extract house rules from JSON data."""
        rules = []
        seen = set()

        for key in ["houseRules", "additionalHouseRules", "listingHouseRules", "guestControls"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, list):
                    for item in val:
                        text = None
                        if isinstance(item, str):
                            text = item
                        elif isinstance(item, dict):
                            text = item.get("title") or item.get("text") or item.get("value", "")
                        if text and text not in seen:
                            seen.add(text)
                            rules.append(text)
                elif isinstance(val, str) and val not in seen:
                    seen.add(val)
                    rules.append(val)

        # Look for check-in/check-out times
        for key in ["checkInTime", "checkIn", "checkinTime"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, (str, int)):
                    text = f"Check-in: {val}"
                    if text not in seen:
                        seen.add(text)
                        rules.append(text)

        for key in ["checkOutTime", "checkOut", "checkoutTime"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, (str, int)):
                    text = f"Check-out: {val}"
                    if text not in seen:
                        seen.add(text)
                        rules.append(text)

        return rules[:20]

    def _parse_location(self, data: Any) -> str:
        """Extract location string from JSON data."""
        # Try direct location fields
        for key in ["locationTitle", "location", "city", "locationDescription"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, str) and 3 < len(val) < 200:
                    return val

        # Try composing from city/state/country
        found = _recursive_find(data, {"city", "state", "country", "neighborhood"})
        parts = []
        for k in ["neighborhood", "city", "state", "country"]:
            v = found.get(k)
            if isinstance(v, str) and v:
                parts.append(v)
        if parts:
            return ", ".join(parts)

        return ""

    def _parse_reviews(self, data: Any) -> dict[str, Any]:
        """Extract review information from JSON data."""
        result: dict[str, Any] = {}

        # Rating
        for key in ["overallRating", "rating", "guestSatisfactionOverall", "starRating",
                     "avgRating", "overallGuestSatisfaction"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, (int, float)) and 0 < val <= 5:
                    result["rating"] = round(val, 2)
                    break
            if "rating" in result:
                break

        # Review count
        for key in ["reviewCount", "reviewsCount", "visibleReviewCount", "totalReviewCount",
                     "overallCount"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, int) and val > 0:
                    result["count"] = val
                    break
            if "count" in result:
                break

        # Category ratings (from StayPdpReviewsSection.ratings)
        category_ratings = []
        ratings_values = _find_all_values(data, "ratings")
        for ratings_list in ratings_values:
            if isinstance(ratings_list, list):
                for item in ratings_list:
                    if isinstance(item, dict) and item.get("__typename") == "CategoryRating":
                        label = item.get("label", "")
                        score = item.get("localizedRating", "")
                        if label and score:
                            category_ratings.append(f"{label}: {score}")
                if category_ratings:
                    break
        if category_ratings:
            result["category_ratings"] = category_ratings

        return result

    def _parse_host_info(self, data: Any) -> dict[str, Any]:
        """Extract host information from JSON data."""
        result: dict[str, Any] = {}

        # Try MeetYourHostSection → cardData → name (most reliable for niobeClientData)
        sections = _find_all_values(data, "sections")
        for sec_list in sections:
            if isinstance(sec_list, list):
                for sec_wrapper in sec_list:
                    if isinstance(sec_wrapper, dict):
                        sec = sec_wrapper.get("section", sec_wrapper)
                        if sec.get("__typename") == "MeetYourHostSection":
                            card = sec.get("cardData", {})
                            if isinstance(card, dict):
                                name = card.get("name", "")
                                if isinstance(name, str) and len(name) > 1:
                                    result["name"] = name.strip()
                                if card.get("isSuperhost"):
                                    result["superhost"] = True
                                return result

        # Fallback: search for hostName specifically (avoid generic "name")
        for key in ["hostName"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, str) and 1 < len(val) < 80:
                    result["name"] = val
                    break
            if "name" in result:
                break

        # Superhost status
        for key in ["isSuperhost", "isSuperHost", "superhost"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, bool):
                    result["superhost"] = val
                    break
            if "superhost" in result:
                break

        return result

    def _parse_photo_count(self, data: Any) -> int:
        """Extract photo count from JSON data."""
        for key in ["photos", "images", "listingPhotos", "photoUrls"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, list) and len(val) > 0:
                    return len(val)

        # Try photoCount field
        for key in ["photoCount", "pictureCount"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, int) and val > 0:
                    return val

        return 0

    def _parse_property_type(self, data: Any) -> str:
        """Extract property type from JSON data."""
        for key in ["roomType", "propertyType", "roomTypeCategory", "listingRoomType",
                     "propertyTypeCategory", "spaceType"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, str) and 2 < len(val) < 100:
                    return val

        return ""

    def _parse_layout(self, data: Any) -> str:
        """Extract layout info (bedrooms, beds, bathrooms, guests) from JSON data."""
        parts = []

        key_map = {
            "personCapacity": "guests",
            "guestCapacity": "guests",
            "guestLabel": None,
            "bedroomCount": "bedrooms",
            "bedrooms": "bedrooms",
            "bedroomLabel": None,
            "bedCount": "beds",
            "beds": "beds",
            "bedLabel": None,
            "bathroomCount": "bathrooms",
            "bathrooms": "bathrooms",
            "bathroomLabel": None,
        }

        found_values: dict[str, str] = {}
        for key, label in key_map.items():
            values = _find_all_values(data, key)
            for val in values:
                if label and isinstance(val, (int, float)) and val > 0 and label not in found_values:
                    found_values[label] = f"{int(val)} {label}"
                elif label is None and isinstance(val, str) and len(val) < 50:
                    # Label fields like "2 bedrooms" - use directly
                    parts.append(val)

        # Use found numeric values if we didn't get labels
        for label_key in ["guests", "bedrooms", "beds", "bathrooms"]:
            if label_key in found_values:
                # Only add if we don't already have a label covering this
                if not any(label_key in p.lower() for p in parts):
                    parts.append(found_values[label_key])

        return " · ".join(parts) if parts else ""

    def _parse_neighbourhood(self, data: Any) -> str:
        """Extract neighbourhood description from JSON data."""
        for key in ["neighborhoodDescription", "neighbourhoodDescription",
                     "locationDescription", "neighborhoodOverview", "neighborhood"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, str) and len(val) > 20:
                    clean = re.sub(r"<[^>]+>", " ", val).strip()
                    clean = re.sub(r"\s+", " ", clean)
                    return clean[:1000]

        # Look for nearby landmarks / transit
        for key in ["gettingAround", "transit", "nearbyLandmarks"]:
            values = _find_all_values(data, key)
            for val in values:
                if isinstance(val, str) and len(val) > 10:
                    clean = re.sub(r"<[^>]+>", " ", val).strip()
                    return clean[:1000]

        return ""

    # --- DOM-based fallback methods ---

    async def _scrape_from_dom(self, page, title: str, url: str) -> ScrapedItem:
        """Fall back to DOM-based extraction (original approach)."""
        property_type = await self._extract_property_type(page)
        location = await self._extract_location(page)
        layout = await self._extract_layout_dom(page)
        amenities = await self._extract_amenities(page)
        house_rules = await self._extract_house_rules_dom(page)
        description = await self._extract_description(page)

        content = self._format_listing(
            title=title,
            url=url,
            property_type=property_type,
            location=location,
            layout=layout,
            amenities=amenities,
            house_rules=house_rules,
            description=description,
        )

        return ScrapedItem(
            title=f"Airbnb: {title}",
            content=content,
            url=url,
            topics=self.default_topics.copy(),
            metadata={
                "source": "airbnb",
                "property_type": property_type,
                "location": location,
                "layout": layout,
            },
        )

    async def _extract_property_type(self, page) -> str:
        """Extract property type (entire flat, private room, etc.)."""
        try:
            for selector in [
                "[data-testid='listing-card-subtitle']",
                "h2",
                "[class*='type']",
            ]:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    text = (await el.text_content() or "").strip()
                    if any(kw in text.lower() for kw in [
                        "entire", "private", "shared", "room", "flat",
                        "apartment", "house", "cottage", "villa",
                    ]):
                        return text
        except Exception:
            pass
        return ""

    async def _extract_location(self, page) -> str:
        """Extract location / neighbourhood."""
        try:
            for selector in [
                "[data-testid='location']",
                "[class*='location'] span",
                "[class*='Location']",
            ]:
                el = await page.query_selector(selector)
                if el:
                    text = (await el.text_content() or "").strip()
                    if text:
                        return text

            body_text = await page.text_content("body") or ""
            loc_match = re.search(r"(?:located in|neighbourhood|area)\s*:?\s*([^.]+)", body_text, re.I)
            if loc_match:
                return loc_match.group(1).strip()[:100]

        except Exception:
            pass
        return ""

    async def _extract_layout_dom(self, page) -> str:
        """Extract layout info (bedrooms, beds, bathrooms)."""
        try:
            body_text = await page.text_content("body") or ""
            layout_match = re.search(
                r"(\d+\s*guest[s]?.*?(?:bathroom|bath)s?)",
                body_text,
                re.I,
            )
            if layout_match:
                return layout_match.group(1).strip()
        except Exception:
            pass
        return ""

    async def _extract_amenities(self, page) -> list[str]:
        """Extract key amenities."""
        amenities = []
        try:
            for selector in [
                "[data-testid='amenity'] span",
                "[class*='amenity'] span",
                "[class*='Amenity'] span",
            ]:
                elements = await page.query_selector_all(selector)
                if elements:
                    for el in elements[:20]:
                        text = (await el.text_content() or "").strip()
                        if text and len(text) < 100:
                            amenities.append(text)
                    break
        except Exception:
            pass
        return amenities

    async def _extract_house_rules_dom(self, page) -> list[str]:
        """Extract house rules."""
        rules = []
        try:
            for selector in [
                "[data-testid='house-rules'] li",
                "[class*='house-rule'] li",
                "[class*='HouseRule'] li",
            ]:
                elements = await page.query_selector_all(selector)
                if elements:
                    for el in elements:
                        text = (await el.text_content() or "").strip()
                        if text:
                            rules.append(text)
                    break
        except Exception:
            pass
        return rules

    async def _extract_description(self, page) -> str:
        """Extract the listing description."""
        try:
            for selector in [
                "[data-testid='description']",
                "[class*='description']",
                "[class*='Description']",
            ]:
                el = await page.query_selector(selector)
                if el:
                    text = (await el.text_content() or "").strip()
                    if text and len(text) > 50:
                        return text[:2000]
        except Exception:
            pass
        return ""

    def _format_listing(
        self,
        title: str,
        url: str,
        property_type: str,
        location: str,
        layout: str,
        amenities: list[str],
        house_rules: list[str],
        description: str,
        reviews: Optional[dict[str, Any]] = None,
        host_info: Optional[dict[str, Any]] = None,
        photo_count: int = 0,
        neighbourhood: str = "",
    ) -> str:
        """Format Airbnb listing as structured markdown."""
        lines = [f"# {title}"]
        lines.append(f"**Source:** Airbnb | **URL:** {url}")

        meta_parts = []
        if property_type:
            meta_parts.append(f"**Type:** {property_type}")
        if location:
            meta_parts.append(f"**Location:** {location}")
        if layout:
            meta_parts.append(f"**Layout:** {layout}")
        if photo_count:
            meta_parts.append(f"**Photos:** {photo_count}")
        if meta_parts:
            lines.append(" | ".join(meta_parts))

        # Host info
        if host_info and host_info.get("name"):
            host_line = f"**Host:** {host_info['name']}"
            if host_info.get("superhost"):
                host_line += " (Superhost)"
            lines.append(host_line)

        # Reviews summary
        if reviews:
            review_parts = []
            if reviews.get("rating"):
                review_parts.append(f"**Rating:** {reviews['rating']}/5")
            if reviews.get("count"):
                review_parts.append(f"**Reviews:** {reviews['count']}")
            if review_parts:
                lines.append(" | ".join(review_parts))
            if reviews.get("category_ratings"):
                lines.append("**Scores:** " + " | ".join(reviews["category_ratings"]))

        lines.append("")

        if description:
            lines.append("## Description")
            lines.append(description)
            lines.append("")

        if neighbourhood:
            lines.append("## Neighbourhood / Location")
            lines.append(neighbourhood)
            lines.append("")

        if amenities:
            lines.append("## Amenities")
            for amenity in amenities:
                lines.append(f"- {amenity}")
            lines.append("")

        if house_rules:
            lines.append("## House Rules")
            for rule in house_rules:
                lines.append(f"- {rule}")
            lines.append("")

        return "\n".join(lines)
