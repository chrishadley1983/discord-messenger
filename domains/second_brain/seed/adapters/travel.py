"""Travel booking adapter.

Scans Gmail for booking confirmations from travel providers (airlines, hotels,
trains), extracts structured data via JSON-LD and Claude AI parsing, and stores
rich travel intelligence in Second Brain.

Supports: British Airways, Airbnb, Booking.com, Trainline, Premier Inn,
easyJet, Hotels.com, and generic booking emails.

Airbnb listing scraping is handled by the existing email_links adapter.
This adapter focuses on extracting booking-specific data (dates, refs, costs)
from confirmation emails, plus check-in instruction emails sent separately.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from logger import logger
from ...config import HADLEY_API_BASE
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


# --- Provider definitions ---

@dataclass
class ProviderConfig:
    """Configuration for a travel email provider."""
    name: str
    gmail_query: str
    topics: list[str]
    booking_type: str  # flight, hotel, train, generic
    has_jsonld: bool = False
    check_in_query: str = ""  # Separate query for check-in instruction emails
    subject_reject_patterns: list[str] = field(default_factory=list)  # Reject emails matching these subject patterns


PROVIDERS: list[ProviderConfig] = [
    ProviderConfig(
        name="british-airways",
        gmail_query='from:ba.com OR from:britishairways.com subject:(booking OR confirmation OR itinerary OR e-ticket)',
        topics=["travel", "flight", "british-airways"],
        booking_type="flight",
        has_jsonld=False,
        check_in_query='from:ba.com OR from:britishairways.com subject:("check-in" OR "check in" OR "boarding")',
    ),
    ProviderConfig(
        name="airbnb",
        gmail_query='from:airbnb subject:(reservation OR "booking confirmed" OR "reservation confirmed" OR receipt)',
        topics=["travel", "accommodation", "airbnb"],
        booking_type="hotel",
        has_jsonld=True,
        check_in_query='from:airbnb subject:("check-in" OR "arriving" OR "your stay" OR "trip to")',
    ),
    ProviderConfig(
        name="booking-com",
        gmail_query='from:booking.com subject:(confirmation OR booking OR reservation) -subject:newsletter -subject:deals -subject:"price drop"',
        topics=["travel", "accommodation", "booking-com"],
        booking_type="hotel",
        has_jsonld=True,
        subject_reject_patterns=["newsletter", "deals", "price drop", "explore", "unsubscribe"],
    ),
    ProviderConfig(
        name="trainline",
        gmail_query='from:trainline subject:(booking OR confirmation OR itinerary) -subject:spotify -subject:railcard -subject:alert -subject:password -subject:"sign in" -subject:newsletter',
        topics=["travel", "train", "trainline"],
        booking_type="train",
        has_jsonld=True,
        subject_reject_patterns=["password", "sign in", "spotify", "railcard", "alert", "newsletter", "unsubscribe"],
    ),
    ProviderConfig(
        name="premier-inn",
        gmail_query='from:premierinn.com subject:(booking OR confirmation OR reservation)',
        topics=["travel", "accommodation", "premier-inn"],
        booking_type="hotel",
        has_jsonld=False,
    ),
    ProviderConfig(
        name="easyjet",
        gmail_query='from:easyjet.com subject:(booking OR confirmation OR itinerary) -subject:sale -subject:deals -subject:newsletter',
        topics=["travel", "flight", "easyjet"],
        booking_type="flight",
        has_jsonld=False,
        check_in_query='from:easyjet.com subject:("check-in" OR "check in" OR "boarding")',
        subject_reject_patterns=["sale", "deals", "newsletter", "unsubscribe"],
    ),
    ProviderConfig(
        name="ryanair",
        gmail_query='from:ryanair.com OR from:ryanair subject:(booking OR confirmation OR itinerary OR "travel itinerary" OR "flight delay") -subject:"gift card" -subject:sale -subject:discover -subject:"rate your"',
        topics=["travel", "flight", "ryanair"],
        booking_type="flight",
        has_jsonld=False,
        check_in_query='from:ryanair OR from:ryanairemail subject:("check in" OR "check-in" OR boarding)',
        subject_reject_patterns=["gift card", "sale", "discover", "rate your experience", "goodbye", "unsubscribe", "password", "reset", "verification code", "win a"],
    ),
    ProviderConfig(
        name="beeksebergen",
        gmail_query='from:libemafunfactory OR from:beeksebergen subject:(booking OR confirmation OR reservation OR receipt OR payment) -subject:cancelled -subject:cancellation',
        topics=["travel", "accommodation", "beeksebergen", "holiday-park"],
        booking_type="hotel",
        has_jsonld=False,
        check_in_query='from:libemafunfactory OR from:beeksebergen subject:("check-in" OR arrival OR "your stay" OR "welcome")',
        subject_reject_patterns=["cancelled", "cancellation", "abandoned", "cart", "wishlist", "browse", "inspiration"],
    ),
    ProviderConfig(
        name="lalandia",
        gmail_query='from:lalandia subject:(booking OR confirmation OR reservation OR receipt)',
        topics=["travel", "accommodation", "lalandia", "holiday-park"],
        booking_type="hotel",
        has_jsonld=False,
        check_in_query='from:lalandia subject:("check-in" OR arrival OR "your stay" OR "welcome")',
    ),
    ProviderConfig(
        name="shinkansen",
        gmail_query='from:expy.jp subject:(reservation OR confirmation OR "reservation confirmation")',
        topics=["travel", "train", "shinkansen", "japan"],
        booking_type="train",
        has_jsonld=False,
        subject_reject_patterns=["one-time password", "membership registration", "membership information"],
    ),
    ProviderConfig(
        name="justpark",
        gmail_query='from:justpark.com subject:(booking OR confirmation OR payment OR receipt) -subject:MOT -subject:welcome -subject:newsletter',
        topics=["travel", "parking", "justpark"],
        booking_type="parking",
        has_jsonld=False,
        subject_reject_patterns=["mot", "welcome", "newsletter", "cancelled"],
    ),
]


# --- HTML text extraction ---

def _html_to_text(html: str) -> str:
    """Strip HTML tags and CSS to extract readable text from email HTML."""
    text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</?(div|p|tr|td|th|table|li|h[1-6])[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&#\d+;', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 2]
    return '\n'.join(lines)


# --- JSON-LD extraction ---

JSONLD_TYPES = {
    "FlightReservation", "LodgingReservation", "TrainReservation",
    "EventReservation", "BusReservation", "RentalCarReservation",
}


def extract_jsonld(html: str) -> list[dict]:
    """Extract schema.org JSON-LD reservation objects from HTML email."""
    results = []
    # Find all <script type="application/ld+json"> blocks
    for match in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE
    ):
        try:
            data = json.loads(match.group(1).strip())
            # Could be a single object or an array
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    item_type = item.get("@type", "")
                    if item_type in JSONLD_TYPES:
                        results.append(item)
                    # Check @graph array
                    for graph_item in item.get("@graph", []):
                        if isinstance(graph_item, dict) and graph_item.get("@type", "") in JSONLD_TYPES:
                            results.append(graph_item)
        except (json.JSONDecodeError, TypeError):
            continue
    return results


def format_jsonld_reservation(reservation: dict) -> dict[str, Any]:
    """Convert a JSON-LD reservation into a flat dict of useful fields."""
    result: dict[str, Any] = {
        "confirmation_number": reservation.get("reservationNumber", ""),
        "status": reservation.get("reservationStatus", "").replace("http://schema.org/Reservation", "").replace("Reservation", ""),
    }

    rtype = reservation.get("@type", "")

    if rtype == "FlightReservation":
        flight = reservation.get("reservationFor", {})
        airline = flight.get("airline", {})
        result.update({
            "type": "flight",
            "flight_number": f"{airline.get('iataCode', '')}{flight.get('flightNumber', '')}",
            "airline": airline.get("name", ""),
            "departure_airport": flight.get("departureAirport", {}).get("iataCode", ""),
            "departure_name": flight.get("departureAirport", {}).get("name", ""),
            "departure_time": flight.get("departureTime", ""),
            "departure_terminal": flight.get("departureTerminal", ""),
            "arrival_airport": flight.get("arrivalAirport", {}).get("iataCode", ""),
            "arrival_name": flight.get("arrivalAirport", {}).get("name", ""),
            "arrival_time": flight.get("arrivalTime", ""),
            "arrival_terminal": flight.get("arrivalTerminal", ""),
            "seat": reservation.get("airplaneSeat", ""),
            "cabin_class": reservation.get("airplaneSeatClass", {}).get("name", "") if isinstance(reservation.get("airplaneSeatClass"), dict) else reservation.get("airplaneSeatClass", ""),
            "checkin_url": reservation.get("checkinUrl", ""),
            "ticket_number": reservation.get("ticketNumber", ""),
            "ticket_download_url": reservation.get("ticketDownloadUrl", ""),
            "web_checkin_time": flight.get("webCheckinTime", ""),
        })

    elif rtype == "LodgingReservation":
        hotel = reservation.get("reservationFor", {})
        address = hotel.get("address", {})
        result.update({
            "type": "hotel",
            "hotel_name": hotel.get("name", ""),
            "hotel_address": _format_address(address),
            "hotel_phone": hotel.get("telephone", ""),
            "checkin_date": reservation.get("checkinDate", "") or reservation.get("checkinTime", ""),
            "checkout_date": reservation.get("checkoutDate", "") or reservation.get("checkoutTime", ""),
            "room_type": reservation.get("lodgingUnitDescription", ""),
            "num_adults": reservation.get("numAdults", ""),
            "num_children": reservation.get("numChildren", ""),
            "price": reservation.get("totalPrice", "") or reservation.get("price", ""),
            "currency": reservation.get("priceCurrency", ""),
            "checkin_url": reservation.get("checkinUrl", ""),
        })

    elif rtype == "TrainReservation":
        trip = reservation.get("reservationFor", {})
        result.update({
            "type": "train",
            "departure_station": trip.get("departureStation", {}).get("name", "") if isinstance(trip.get("departureStation"), dict) else trip.get("departureStation", ""),
            "departure_time": trip.get("departureTime", ""),
            "departure_platform": trip.get("departurePlatform", ""),
            "arrival_station": trip.get("arrivalStation", {}).get("name", "") if isinstance(trip.get("arrivalStation"), dict) else trip.get("arrivalStation", ""),
            "arrival_time": trip.get("arrivalTime", ""),
            "train_number": trip.get("trainNumber", ""),
            "train_name": trip.get("trainName", ""),
            "operator": trip.get("trainCompany", {}).get("name", "") if isinstance(trip.get("trainCompany"), dict) else trip.get("trainCompany", ""),
            "seat": reservation.get("reservedTicket", {}).get("ticketedSeat", {}).get("seatNumber", ""),
            "carriage": reservation.get("reservedTicket", {}).get("ticketedSeat", {}).get("seatRow", ""),
            "ticket_download_url": reservation.get("reservedTicket", {}).get("url", "") or reservation.get("ticketDownloadUrl", ""),
        })

    # Passenger info
    under_name = reservation.get("underName", {})
    if isinstance(under_name, dict):
        result["passenger_name"] = under_name.get("name", "")

    # Action URLs
    for key in ("confirmReservationUrl", "cancelReservationUrl", "modifyReservationUrl"):
        val = reservation.get(key, "")
        if isinstance(val, dict):
            val = val.get("url", "") or val.get("target", "")
        if val:
            result[key] = val

    return {k: v for k, v in result.items() if v}


def _format_address(address: Any) -> str:
    """Format a schema.org PostalAddress into a string."""
    if isinstance(address, str):
        return address
    if not isinstance(address, dict):
        return ""
    parts = []
    for key in ["streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"]:
        val = address.get(key, "")
        if isinstance(val, dict):
            val = val.get("name", "")
        if val:
            parts.append(str(val))
    return ", ".join(parts)


# --- Claude AI extraction ---

FLIGHT_EXTRACTION_PROMPT = """Extract travel booking details from this email. Return ONLY valid JSON with these fields (omit any that are not found):

{{
  "type": "flight",
  "airline": "airline name",
  "flight_number": "e.g. BA007",
  "confirmation_number": "booking reference / PNR",
  "ticket_number": "e-ticket number",
  "departure_airport": "IATA code",
  "departure_name": "airport name",
  "departure_time": "ISO datetime or date string",
  "departure_terminal": "terminal",
  "arrival_airport": "IATA code",
  "arrival_name": "airport name",
  "arrival_time": "ISO datetime or date string",
  "arrival_terminal": "terminal",
  "passenger_name": "passenger name(s)",
  "seat": "seat if assigned",
  "cabin_class": "economy/business/first",
  "baggage": "baggage allowance",
  "manage_booking_url": "link to manage booking",
  "checkin_url": "link to check in",
  "price": "total price",
  "currency": "GBP/USD etc",
  "outbound_flights": [{{same fields for each leg}}],
  "return_flights": [{{same fields for each leg}}],
  "notes": "any important warnings, requirements, or deadlines"
}}

If there are multiple flights (outbound + return, or connections), include them in the outbound_flights/return_flights arrays.

Email content:
{email_text}"""

HOTEL_EXTRACTION_PROMPT = """Extract hotel/accommodation booking details from this email. Return ONLY valid JSON with these fields (omit any that are not found):

{{
  "type": "hotel",
  "hotel_name": "property name",
  "confirmation_number": "booking reference",
  "hotel_address": "full address",
  "hotel_phone": "phone number",
  "checkin_date": "check-in date/time",
  "checkout_date": "check-out date/time",
  "room_type": "room description",
  "num_nights": number,
  "num_adults": number,
  "num_children": number,
  "price": "total price",
  "currency": "GBP/USD etc",
  "price_breakdown": "nightly rate, cleaning fee, etc if available",
  "cancellation_policy": "free cancellation until X, or non-refundable etc",
  "cancellation_deadline": "date by which you can cancel free",
  "meals_included": "breakfast/half-board/none",
  "parking": "parking info if mentioned",
  "wifi": "wifi info if mentioned",
  "special_requests": "any noted special requests",
  "host_name": "host name (for Airbnb etc)",
  "manage_booking_url": "link to manage booking",
  "checkin_instructions": "check-in procedure if mentioned",
  "pin_code": "property PIN code if mentioned",
  "passenger_name": "guest name(s)",
  "notes": "any important warnings, requirements, document requests, or deadlines"
}}

Email content:
{email_text}"""

TRAIN_EXTRACTION_PROMPT = """Extract train booking details from this email. Return ONLY valid JSON with these fields (omit any that are not found):

{{
  "type": "train",
  "confirmation_number": "booking reference",
  "departure_station": "station name",
  "departure_time": "departure date/time",
  "departure_platform": "platform if known",
  "arrival_station": "station name",
  "arrival_time": "arrival date/time",
  "operator": "train company (LNER, Avanti, etc)",
  "train_number": "train number if shown",
  "seat": "seat number",
  "carriage": "carriage/coach letter or number",
  "ticket_type": "advance/off-peak/anytime etc",
  "railcard": "railcard used if any",
  "collection_method": "e-ticket / collect at station / smartcard",
  "ticket_download_url": "link to download tickets",
  "price": "total price",
  "currency": "GBP",
  "passenger_name": "passenger name(s)",
  "outbound_journeys": [{{same fields for each leg}}],
  "return_journeys": [{{same fields for each leg}}],
  "notes": "any important info about restrictions, changes, or conditions"
}}

If there are multiple journeys (outbound + return, or connections), include them in the arrays.

Email content:
{email_text}"""

CHECKIN_EXTRACTION_PROMPT = """Extract check-in and pre-arrival details from this email. Return ONLY valid JSON with these fields (omit any that are not found):

{{
  "type": "checkin_instructions",
  "provider": "airline/hotel/airbnb name",
  "confirmation_number": "booking reference if mentioned",
  "checkin_instructions": "full check-in procedure (door codes, key boxes, reception hours etc)",
  "checkin_time": "check-in time/window",
  "checkout_time": "check-out time",
  "wifi_password": "wifi details if provided",
  "door_code": "entry code if provided",
  "key_collection": "how to get keys",
  "host_phone": "host/property phone number",
  "host_name": "host name",
  "parking_instructions": "parking details",
  "house_rules": ["list of house rules"],
  "required_documents": "any documents requested (passport, ID etc)",
  "document_deadline": "deadline for submitting documents",
  "directions": "directions to property",
  "emergency_contact": "emergency contact info",
  "notes": "any other important pre-arrival info"
}}

Email content:
{email_text}"""


PARKING_EXTRACTION_PROMPT = """Extract parking booking details from this email. Return ONLY valid JSON with these fields (omit any that are not found):

{{
  "type": "parking",
  "confirmation_number": "booking ID / reference",
  "parking_location": "address or location name",
  "start_date": "parking start date/time",
  "end_date": "parking end date/time",
  "vehicle_registration": "VRM / number plate",
  "price": "total price",
  "currency": "GBP/USD etc",
  "access_instructions": "how to access the parking space",
  "cancellation_policy": "cancellation terms",
  "cancellation_deadline": "free cancellation deadline",
  "passenger_name": "booker name",
  "manage_booking_url": "link to manage booking",
  "notes": "any important info"
}}

Email content:
{email_text}"""

EXTRACTION_PROMPTS = {
    "flight": FLIGHT_EXTRACTION_PROMPT,
    "hotel": HOTEL_EXTRACTION_PROMPT,
    "train": TRAIN_EXTRACTION_PROMPT,
    "checkin": CHECKIN_EXTRACTION_PROMPT,
    "generic": HOTEL_EXTRACTION_PROMPT,
    "parking": PARKING_EXTRACTION_PROMPT,
}


async def claude_extract_booking(
    email_text: str, booking_type: str, api_base: str = HADLEY_API_BASE
) -> Optional[dict]:
    """Use Claude CLI via Hadley API to extract booking details from email text."""
    prompt_template = EXTRACTION_PROMPTS.get(booking_type, HOTEL_EXTRACTION_PROMPT)
    prompt = prompt_template.replace("{email_text}", email_text[:6000])

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{api_base}/claude/extract",
                json={"prompt": prompt, "max_tokens": 1500},
                timeout=90,
            )
            if resp.status_code != 200:
                logger.warning(f"Claude extract API returned {resp.status_code}")
                return None
            data = resp.json()
            if data.get("error"):
                logger.warning(f"Claude extract error: {data['error']}")
                return None
            response = data.get("result")
    except Exception as e:
        logger.warning(f"Claude extract request failed: {e}")
        return None

    if not response:
        return None

    # Parse JSON from response (Claude may wrap it in markdown code blocks)
    json_str = response.strip()
    if json_str.startswith("```"):
        json_str = re.sub(r'^```(?:json)?\s*', '', json_str)
        json_str = re.sub(r'\s*```$', '', json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse Claude extraction response as JSON")
        return None


# --- Formatting ---

def format_booking_markdown(data: dict, provider_name: str, email_subject: str) -> str:
    """Format extracted booking data as rich markdown for Second Brain."""
    booking_type = data.get("type", "generic")
    lines = []

    if booking_type == "flight":
        title = _flight_title(data)
        lines.append(f"# {title}")
        lines.append(f"**Provider:** {provider_name} | **Type:** Flight")

        if data.get("confirmation_number"):
            lines.append(f"**Booking Ref:** {data['confirmation_number']}")
        if data.get("ticket_number"):
            lines.append(f"**E-Ticket:** {data['ticket_number']}")
        if data.get("passenger_name"):
            lines.append(f"**Passenger:** {data['passenger_name']}")
        if data.get("cabin_class"):
            lines.append(f"**Class:** {data['cabin_class']}")
        if data.get("price"):
            lines.append(f"**Price:** {data.get('currency', '')} {data['price']}")
        lines.append("")

        # Main flight or outbound
        if data.get("departure_airport"):
            lines.append("## Flight Details")
            lines.append(_format_flight_leg(data))
            lines.append("")

        # Multiple legs
        for label, key in [("Outbound", "outbound_flights"), ("Return", "return_flights")]:
            legs = data.get(key, [])
            if legs:
                lines.append(f"## {label}")
                for i, leg in enumerate(legs, 1):
                    if len(legs) > 1:
                        lines.append(f"### Leg {i}")
                    lines.append(_format_flight_leg(leg))
                    lines.append("")

        if data.get("baggage"):
            lines.append(f"**Baggage:** {data['baggage']}")
        if data.get("seat"):
            lines.append(f"**Seat:** {data['seat']}")
        if data.get("manage_booking_url"):
            lines.append(f"**Manage Booking:** {data['manage_booking_url']}")
        if data.get("checkin_url"):
            lines.append(f"**Check-in:** {data['checkin_url']}")

    elif booking_type == "hotel":
        hotel = data.get("hotel_name", "Hotel")
        lines.append(f"# {hotel}")
        lines.append(f"**Provider:** {provider_name} | **Type:** Accommodation")

        if data.get("confirmation_number"):
            lines.append(f"**Booking Ref:** {data['confirmation_number']}")
        if data.get("passenger_name"):
            lines.append(f"**Guest:** {data['passenger_name']}")
        if data.get("hotel_address"):
            lines.append(f"**Address:** {data['hotel_address']}")
        if data.get("hotel_phone"):
            lines.append(f"**Phone:** {data['hotel_phone']}")
        lines.append("")

        lines.append("## Stay Details")
        if data.get("checkin_date"):
            lines.append(f"- **Check-in:** {data['checkin_date']}")
        if data.get("checkout_date"):
            lines.append(f"- **Check-out:** {data['checkout_date']}")
        if data.get("num_nights"):
            lines.append(f"- **Nights:** {data['num_nights']}")
        if data.get("room_type"):
            lines.append(f"- **Room:** {data['room_type']}")
        guests = []
        if data.get("num_adults"):
            guests.append(f"{data['num_adults']} adults")
        if data.get("num_children"):
            guests.append(f"{data['num_children']} children")
        if guests:
            lines.append(f"- **Guests:** {', '.join(guests)}")
        if data.get("meals_included"):
            lines.append(f"- **Meals:** {data['meals_included']}")
        lines.append("")

        if data.get("price"):
            lines.append(f"**Price:** {data.get('currency', '')} {data['price']}")
        if data.get("price_breakdown"):
            lines.append(f"**Breakdown:** {data['price_breakdown']}")

        if data.get("cancellation_policy"):
            lines.append("")
            lines.append(f"## Cancellation Policy")
            lines.append(data["cancellation_policy"])
            if data.get("cancellation_deadline"):
                lines.append(f"**Deadline:** {data['cancellation_deadline']}")

        if data.get("parking"):
            lines.append(f"\n**Parking:** {data['parking']}")
        if data.get("wifi"):
            lines.append(f"**WiFi:** {data['wifi']}")

        if data.get("host_name"):
            lines.append(f"\n**Host:** {data['host_name']}")
        if data.get("checkin_instructions"):
            lines.append(f"\n## Check-in Instructions")
            lines.append(data["checkin_instructions"])

        if data.get("manage_booking_url"):
            lines.append(f"\n**Manage Booking:** {data['manage_booking_url']}")

    elif booking_type == "train":
        title = _train_title(data)
        lines.append(f"# {title}")
        lines.append(f"**Provider:** {provider_name} | **Type:** Train")

        if data.get("confirmation_number"):
            lines.append(f"**Booking Ref:** {data['confirmation_number']}")
        if data.get("passenger_name"):
            lines.append(f"**Passenger:** {data['passenger_name']}")
        if data.get("ticket_type"):
            lines.append(f"**Ticket Type:** {data['ticket_type']}")
        if data.get("railcard"):
            lines.append(f"**Railcard:** {data['railcard']}")
        if data.get("price"):
            lines.append(f"**Price:** {data.get('currency', '')} {data['price']}")
        if data.get("collection_method"):
            lines.append(f"**Collection:** {data['collection_method']}")
        lines.append("")

        # Main journey or legs
        if data.get("departure_station"):
            lines.append("## Journey Details")
            lines.append(_format_train_leg(data))
            lines.append("")

        for label, key in [("Outbound", "outbound_journeys"), ("Return", "return_journeys")]:
            legs = data.get(key, [])
            if legs:
                lines.append(f"## {label}")
                for i, leg in enumerate(legs, 1):
                    if len(legs) > 1:
                        lines.append(f"### Leg {i}")
                    lines.append(_format_train_leg(leg))
                    lines.append("")

        if data.get("ticket_download_url"):
            lines.append(f"**Download Tickets:** {data['ticket_download_url']}")

    elif booking_type == "parking":
        location = data.get("parking_location", "Parking")
        lines.append(f"# Parking — {location}")
        lines.append(f"**Provider:** {provider_name} | **Type:** Parking")

        if data.get("confirmation_number"):
            lines.append(f"**Booking Ref:** {data['confirmation_number']}")
        if data.get("passenger_name"):
            lines.append(f"**Booked by:** {data['passenger_name']}")
        if data.get("vehicle_registration"):
            lines.append(f"**Vehicle:** {data['vehicle_registration']}")
        lines.append("")

        if data.get("start_date"):
            lines.append(f"- **From:** {data['start_date']}")
        if data.get("end_date"):
            lines.append(f"- **Until:** {data['end_date']}")
        if data.get("price"):
            lines.append(f"- **Price:** {data.get('currency', '')} {data['price']}")
        lines.append("")

        if data.get("parking_location"):
            lines.append(f"**Location:** {data['parking_location']}")
        if data.get("access_instructions"):
            lines.append(f"\n## Access Instructions")
            lines.append(data["access_instructions"])

        if data.get("cancellation_policy"):
            lines.append(f"\n**Cancellation:** {data['cancellation_policy']}")
        if data.get("cancellation_deadline"):
            lines.append(f"**Cancel by:** {data['cancellation_deadline']}")
        if data.get("manage_booking_url"):
            lines.append(f"\n**Manage Booking:** {data['manage_booking_url']}")

    elif booking_type == "checkin_instructions":
        provider = data.get("provider", provider_name)
        lines.append(f"# Check-in Instructions — {provider}")
        lines.append(f"**Provider:** {provider_name} | **Type:** Check-in Info")

        if data.get("confirmation_number"):
            lines.append(f"**Booking Ref:** {data['confirmation_number']}")
        lines.append("")

        if data.get("checkin_time"):
            lines.append(f"**Check-in:** {data['checkin_time']}")
        if data.get("checkout_time"):
            lines.append(f"**Check-out:** {data['checkout_time']}")

        if data.get("checkin_instructions"):
            lines.append(f"\n## How to Check In")
            lines.append(data["checkin_instructions"])

        if data.get("door_code"):
            lines.append(f"\n**Door Code:** {data['door_code']}")
        if data.get("key_collection"):
            lines.append(f"**Keys:** {data['key_collection']}")
        if data.get("wifi_password"):
            lines.append(f"**WiFi:** {data['wifi_password']}")

        if data.get("host_name"):
            lines.append(f"\n**Host:** {data['host_name']}")
        if data.get("host_phone"):
            lines.append(f"**Host Phone:** {data['host_phone']}")
        if data.get("emergency_contact"):
            lines.append(f"**Emergency:** {data['emergency_contact']}")

        if data.get("parking_instructions"):
            lines.append(f"\n**Parking:** {data['parking_instructions']}")
        if data.get("directions"):
            lines.append(f"\n## Directions")
            lines.append(data["directions"])

        if data.get("house_rules"):
            lines.append(f"\n## House Rules")
            for rule in data["house_rules"]:
                lines.append(f"- {rule}")

        if data.get("required_documents"):
            lines.append(f"\n## Required Documents")
            lines.append(f"**Documents needed:** {data['required_documents']}")
            if data.get("document_deadline"):
                lines.append(f"**Deadline:** {data['document_deadline']}")

    else:
        lines.append(f"# Travel Booking — {email_subject}")
        lines.append(f"**Provider:** {provider_name}")
        for key, val in data.items():
            if val and key not in ("type",):
                lines.append(f"**{key.replace('_', ' ').title()}:** {val}")

    # Notes (warnings, deadlines, requirements)
    if data.get("notes"):
        lines.append(f"\n## Important Notes")
        lines.append(data["notes"])

    return "\n".join(lines)


def _flight_title(data: dict) -> str:
    dep = data.get("departure_airport", "")
    arr = data.get("arrival_airport", "")
    airline = data.get("airline", "")
    flight_num = data.get("flight_number", "")
    date = data.get("departure_time", "")[:10]

    # Try outbound flights for multi-leg
    if not dep and data.get("outbound_flights"):
        first = data["outbound_flights"][0]
        dep = first.get("departure_airport", "")
        arr = data["outbound_flights"][-1].get("arrival_airport", "")
        airline = first.get("airline", airline)
        date = first.get("departure_time", "")[:10]

    parts = []
    if airline:
        parts.append(airline)
    if dep and arr:
        parts.append(f"{dep} → {arr}")
    if flight_num and not (dep and arr):
        parts.append(flight_num)
    if date:
        parts.append(date)
    return " — ".join(parts) if parts else "Flight Booking"


def _train_title(data: dict) -> str:
    dep = data.get("departure_station", "")
    arr = data.get("arrival_station", "")
    date = data.get("departure_time", "")[:10]
    operator = data.get("operator", "")

    if not dep and data.get("outbound_journeys"):
        first = data["outbound_journeys"][0]
        dep = first.get("departure_station", "")
        arr = data["outbound_journeys"][-1].get("arrival_station", "")
        date = first.get("departure_time", "")[:10]

    parts = []
    if operator:
        parts.append(operator)
    if dep and arr:
        parts.append(f"{dep} → {arr}")
    if date:
        parts.append(date)
    return " — ".join(parts) if parts else "Train Booking"


def _format_flight_leg(leg: dict) -> str:
    parts = []
    dep = leg.get("departure_airport", "")
    dep_name = leg.get("departure_name", "")
    arr = leg.get("arrival_airport", "")
    arr_name = leg.get("arrival_name", "")
    dep_term = leg.get("departure_terminal", "")
    arr_term = leg.get("arrival_terminal", "")

    dep_str = dep_name or dep
    if dep and dep_name:
        dep_str = f"{dep_name} ({dep})"
    if dep_term:
        dep_str += f" T{dep_term}"

    arr_str = arr_name or arr
    if arr and arr_name:
        arr_str = f"{arr_name} ({arr})"
    if arr_term:
        arr_str += f" T{arr_term}"

    if dep_str:
        parts.append(f"- **From:** {dep_str}")
    if leg.get("departure_time"):
        parts.append(f"- **Departs:** {leg['departure_time']}")
    if arr_str:
        parts.append(f"- **To:** {arr_str}")
    if leg.get("arrival_time"):
        parts.append(f"- **Arrives:** {leg['arrival_time']}")
    if leg.get("flight_number"):
        parts.append(f"- **Flight:** {leg['flight_number']}")
    if leg.get("airline"):
        parts.append(f"- **Airline:** {leg['airline']}")
    if leg.get("seat"):
        parts.append(f"- **Seat:** {leg['seat']}")
    return "\n".join(parts)


def _format_train_leg(leg: dict) -> str:
    parts = []
    if leg.get("departure_station"):
        parts.append(f"- **From:** {leg['departure_station']}")
    if leg.get("departure_time"):
        parts.append(f"- **Departs:** {leg['departure_time']}")
    if leg.get("departure_platform"):
        parts.append(f"- **Platform:** {leg['departure_platform']}")
    if leg.get("arrival_station"):
        parts.append(f"- **To:** {leg['arrival_station']}")
    if leg.get("arrival_time"):
        parts.append(f"- **Arrives:** {leg['arrival_time']}")
    if leg.get("operator"):
        parts.append(f"- **Operator:** {leg['operator']}")
    if leg.get("train_number"):
        parts.append(f"- **Train:** {leg['train_number']}")
    if leg.get("carriage"):
        parts.append(f"- **Carriage:** {leg['carriage']}")
    if leg.get("seat"):
        parts.append(f"- **Seat:** {leg['seat']}")
    return "\n".join(parts)


# --- Main adapter ---

@register_adapter
class TravelBookingAdapter(SeedAdapter):
    """Import travel bookings from Gmail confirmation emails."""

    name = "travel-bookings"
    description = "Extract travel bookings from email confirmations (flights, hotels, trains)"
    source_system = "seed:travel"

    def __init__(self, config: dict[str, Any] = None):
        super().__init__(config)
        self.api_base = config.get("api_base", HADLEY_API_BASE) if config else HADLEY_API_BASE
        self.years_back = config.get("years_back", 1.0) if config else 1.0
        self.per_provider_limit = config.get("per_provider_limit", 20) if config else 20
        self.include_checkin = config.get("include_checkin", True) if config else True

    async def validate(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_base}/gmail/labels", timeout=5)
                if response.status_code == 200:
                    return True, ""
                return False, f"Gmail API returned {response.status_code}"
        except Exception as e:
            return False, f"Cannot reach Gmail API: {e}"

    async def fetch(self, limit: int = 200) -> list[SeedItem]:
        items: list[SeedItem] = []
        after_date = (datetime.now() - timedelta(days=365 * self.years_back)).strftime("%Y/%m/%d")

        async with httpx.AsyncClient(timeout=120) as client:
            for provider in PROVIDERS:
                if len(items) >= limit:
                    break

                try:
                    # Fetch booking confirmation emails
                    booking_items = await self._process_provider(
                        client, provider, after_date,
                        provider.gmail_query, provider.booking_type,
                    )
                    items.extend(booking_items)
                    logger.info(f"[travel:{provider.name}] {len(booking_items)} bookings")

                    # Also fetch check-in instruction emails
                    if self.include_checkin and provider.check_in_query:
                        checkin_items = await self._process_provider(
                            client, provider, after_date,
                            provider.check_in_query, "checkin",
                        )
                        items.extend(checkin_items)
                        if checkin_items:
                            logger.info(f"[travel:{provider.name}] {len(checkin_items)} check-in emails")

                except Exception as e:
                    logger.error(f"[travel:{provider.name}] Failed: {e}")

        return items[:limit]

    async def _process_provider(
        self,
        client: httpx.AsyncClient,
        provider: ProviderConfig,
        after_date: str,
        query: str,
        extraction_type: str,
    ) -> list[SeedItem]:
        """Process emails for a single provider."""
        items: list[SeedItem] = []
        full_query = f"{query} after:{after_date}"

        # Search Gmail
        response = await client.get(
            f"{self.api_base}/gmail/search",
            params={"q": full_query, "limit": self.per_provider_limit * 2},
            timeout=60,
        )
        if response.status_code != 200:
            logger.warning(f"[travel:{provider.name}] Gmail search failed: {response.status_code}")
            return items

        emails = response.json().get("emails", [])
        if not emails:
            return items

        logger.info(f"[travel:{provider.name}] Found {len(emails)} emails for '{extraction_type}'")

        for email in emails[:self.per_provider_limit]:
            email_id = email.get("id")
            if not email_id:
                continue

            try:
                item = await self._process_email(
                    client, provider, email_id, email, extraction_type,
                )
                if item:
                    items.append(item)
            except Exception as e:
                logger.warning(f"[travel:{provider.name}] Email {email_id} failed: {e}")

        return items

    async def _process_email(
        self,
        client: httpx.AsyncClient,
        provider: ProviderConfig,
        email_id: str,
        email_meta: dict,
        extraction_type: str,
    ) -> Optional[SeedItem]:
        """Process a single email into a SeedItem."""
        # Fetch email with HTML
        response = await client.get(
            f"{self.api_base}/gmail/get",
            params={"id": email_id, "html": "true"},
            timeout=30,
        )
        if response.status_code != 200:
            return None

        email_data = response.json()
        subject = email_data.get("subject", "(no subject)")
        body_text = email_data.get("body", "")
        html_body = email_data.get("html", "")
        date_str = email_data.get("date", "")
        attachments = email_data.get("attachments", [])

        # Reject emails matching subject reject patterns
        if provider.subject_reject_patterns:
            subject_lower = subject.lower()
            for pattern in provider.subject_reject_patterns:
                if pattern.lower() in subject_lower:
                    logger.debug(f"[travel:{provider.name}] Rejected '{subject[:50]}' (matches '{pattern}')")
                    return None

        if not body_text and not html_body:
            return None

        # If body_text is actually HTML (common for Ryanair etc), extract readable text
        if body_text and body_text.strip().startswith('<'):
            body_text = _html_to_text(html_body or body_text)
        elif not body_text and html_body:
            body_text = _html_to_text(html_body)

        # Step 0: Extract text from PDF attachments for richer data
        pdf_text = ""
        pdf_attachments = [
            a for a in attachments
            if a.get("filename", "").lower().endswith(".pdf")
            and a.get("attachmentId")
        ]
        for att in pdf_attachments[:3]:  # Max 3 PDFs
            try:
                pdf_resp = await client.get(
                    f"{self.api_base}/gmail/attachment/text",
                    params={"message_id": email_id, "attachment_id": att["attachmentId"]},
                    timeout=30,
                )
                if pdf_resp.status_code == 200:
                    pdf_data = pdf_resp.json()
                    extracted = pdf_data.get("text", "")
                    if extracted and len(extracted) > 50:
                        pdf_text += f"\n\n--- PDF: {att['filename']} ---\n{extracted}"
                        logger.info(f"[travel:{provider.name}] Extracted {len(extracted)} chars from PDF {att['filename']}")
            except Exception as e:
                logger.debug(f"[travel:{provider.name}] PDF extraction failed for {att.get('filename')}: {e}")

        # Step 1: Try JSON-LD extraction from HTML
        booking_data = None
        if html_body and provider.has_jsonld:
            jsonld_items = extract_jsonld(html_body)
            if jsonld_items:
                booking_data = format_jsonld_reservation(jsonld_items[0])
                logger.info(f"[travel:{provider.name}] Extracted JSON-LD from {subject[:50]}")

        # Step 2: Always use Claude for richer extraction
        # Include PDF text alongside email body for fuller context
        extraction_input = body_text[:6000]
        if pdf_text:
            extraction_input = f"{body_text[:4000]}\n{pdf_text[:4000]}"
        claude_data = await claude_extract_booking(extraction_input, extraction_type, self.api_base)

        if claude_data:
            if booking_data:
                # Merge: Claude fills gaps, JSON-LD provides confirmed structured data
                merged = {**claude_data, **{k: v for k, v in booking_data.items() if v}}
                booking_data = merged
            else:
                booking_data = claude_data
                logger.info(f"[travel:{provider.name}] Claude-extracted from {subject[:50]}")

        if not booking_data:
            logger.debug(f"[travel:{provider.name}] No data extracted from {subject[:50]}")
            return None

        # Reject non-booking content (abandoned carts, cancellations, marketing)
        if extraction_type != "checkin" and self._is_junk_booking(booking_data, subject, body_text):
            logger.debug(f"[travel:{provider.name}] Rejected non-booking content: {subject[:50]}")
            return None

        # Note ticket attachments
        ticket_attachments = [
            a for a in attachments
            if a.get("filename", "").lower().endswith((".pdf", ".pkpass"))
            or "ticket" in a.get("filename", "").lower()
            or "boarding" in a.get("filename", "").lower()
            or "itinerary" in a.get("filename", "").lower()
        ]
        if ticket_attachments:
            booking_data["ticket_attachments"] = [
                {"filename": a["filename"], "attachment_id": a.get("attachmentId", "")}
                for a in ticket_attachments
            ]

        # Format as markdown
        content = format_booking_markdown(booking_data, provider.name, subject)

        # Add attachment info to content
        if ticket_attachments:
            content += "\n\n## Attachments"
            for att in ticket_attachments:
                content += f"\n- {att['filename']} ({att.get('mimeType', 'unknown')})"

        # Build dedup key
        conf_num = booking_data.get("confirmation_number", "")
        if conf_num:
            source_url = f"travel://{provider.name}/{conf_num}"
        else:
            # Use email ID as fallback
            source_url = f"travel://{provider.name}/email-{email_id}"

        # If this is a check-in email, append to avoid overwriting the booking
        if extraction_type == "checkin":
            source_url += "/checkin"

        # Parse email date
        created_at = self._parse_date(date_str)

        # Build metadata
        metadata = {
            "provider": provider.name,
            "booking_type": booking_data.get("type", extraction_type),
            "email_subject": subject,
        }
        for key in ["confirmation_number", "departure_time", "checkin_date",
                     "checkout_date", "departure_airport", "arrival_airport",
                     "hotel_name", "departure_station", "arrival_station",
                     "parking_location", "start_date", "end_date",
                     "price", "currency"]:
            if booking_data.get(key):
                metadata[key] = booking_data[key]

        # Determine title
        if extraction_type == "checkin":
            title = f"Check-in: {provider.name} — {subject[:60]}"
        elif booking_data.get("type") == "flight":
            title = f"Flight: {_flight_title(booking_data)}"
        elif booking_data.get("type") == "hotel":
            hotel = booking_data.get("hotel_name", provider.name)
            title = f"Hotel: {hotel}"
        elif booking_data.get("type") == "train":
            title = f"Train: {_train_title(booking_data)}"
        elif booking_data.get("type") == "parking":
            location = booking_data.get("parking_location", provider.name)
            title = f"Parking: {location}"
        else:
            title = f"Booking: {provider.name} — {subject[:60]}"

        topics = list(set(provider.topics + ["travel"]))

        return SeedItem(
            title=title,
            content=content,
            source_url=source_url,
            topics=topics,
            created_at=created_at,
            metadata=metadata,
            content_type="travel_booking",
        )

    @staticmethod
    def _is_junk_booking(data: dict, subject: str, body: str) -> bool:
        """Detect non-booking content: abandoned carts, cancellations, marketing."""
        combined = f"{subject} {body[:500]}".lower()
        # Cancellation / abandoned cart signals
        junk_signals = [
            "cancelled", "cancellation", "has been cancelled",
            "abandoned", "forgot something", "still interested",
            "left something behind", "items in your cart",
            "password reset", "reset your password",
            "unsubscribe", "newsletter",
        ]
        for signal in junk_signals:
            if signal in combined:
                # Allow "free cancellation" in bookings — that's about policy, not cancellation
                if signal in ("cancelled", "cancellation") and "free cancellation" in combined:
                    continue
                return True
        # If Claude extracted nothing meaningful (no ref, no dates, no hotel/airport)
        has_ref = bool(data.get("confirmation_number"))
        has_dates = bool(data.get("departure_time") or data.get("checkin_date") or data.get("departure_station") or data.get("start_date"))
        has_property = bool(data.get("hotel_name") or data.get("departure_airport") or data.get("airline") or data.get("parking_location"))
        if not has_ref and not has_dates and not has_property:
            return True
        return False

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse RFC email date string."""
        if not date_str:
            return None
        for fmt in [
            "%a, %d %b %Y %H:%M:%S %z",
            "%d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S",
        ]:
            try:
                return datetime.strptime(date_str.split(" (")[0].strip(), fmt)
            except ValueError:
                continue
        return None

    def get_default_topics(self) -> list[str]:
        return ["travel"]

    async def discover_unknown_providers(self) -> list[dict[str, Any]]:
        """Scan Gmail for travel booking emails from unknown providers.

        Searches for generic booking/confirmation emails and groups by sender
        domain, filtering out known providers. Returns domains with 2+ emails
        as potential new provider suggestions.
        """
        known_domains = set()
        for provider in PROVIDERS:
            # Extract domains from gmail_query (from:xxx patterns)
            for match in re.finditer(r'from:(\S+)', provider.gmail_query):
                domain = match.group(1).lower()
                known_domains.add(domain)
            if provider.check_in_query:
                for match in re.finditer(r'from:(\S+)', provider.check_in_query):
                    domain = match.group(1).lower()
                    known_domains.add(domain)

        # Also exclude common non-travel senders
        known_domains.update({
            "gmail.com", "google.com", "outlook.com", "hotmail.com",
            "yahoo.com", "proton.me", "protonmail.com", "icloud.com",
            "amazon.co.uk", "amazon.com", "ebay.com", "ebay.co.uk",
            "paypal.com", "paypal.co.uk", "vinted.co.uk", "vinted.com",
            "facebookmail.com", "facebook.com", "instagram.com",
            "uber.com", "bricklink.com", "brickowl.com", "bricqer.com",
            "apple.com", "microsoft.com", "netflix.com", "spotify.com",
            "github.com", "vercel.com", "supabase.io", "supabase.com",
            "monzo.com", "starling.com", "revolut.com",
        })

        # Subject patterns that indicate non-travel emails (2FA, promos, etc)
        junk_subject_patterns = [
            "confirmation code", "one-time password", "otp", "verify your",
            "reset your password", "sign in", "here's £", "here's $",
            "off your first",
        ]

        after_date = (datetime.now() - timedelta(days=365)).strftime("%Y/%m/%d")
        query = f'subject:(booking OR confirmation OR reservation OR itinerary OR "e-ticket" OR "booking reference") after:{after_date}'

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(
                    f"{self.api_base}/gmail/search",
                    params={"q": query, "limit": 200},
                    timeout=60,
                )
                if resp.status_code != 200:
                    return []

                emails = resp.json().get("emails", [])
        except Exception as e:
            logger.warning(f"[travel:discovery] Gmail search failed: {e}")
            return []

        # Group by sender domain
        domain_emails: dict[str, list[dict]] = {}
        for email in emails:
            sender = email.get("from", "")
            subject = email.get("subject", "")

            # Skip 2FA / promo subjects
            subject_lower = subject.lower()
            if any(p in subject_lower for p in junk_subject_patterns):
                continue

            # Extract domain from "Name <user@domain.com>" or "user@domain.com"
            domain_match = re.search(r'@([\w.-]+)', sender)
            if not domain_match:
                continue
            domain = domain_match.group(1).lower()

            # Skip known provider domains
            if any(known in domain or domain in known for known in known_domains):
                continue

            if domain not in domain_emails:
                domain_emails[domain] = []
            domain_emails[domain].append({
                "subject": subject,
                "from": sender,
                "date": email.get("date", ""),
            })

        # Return domains with 2+ booking emails as suggestions
        suggestions = []
        for domain, emails_list in sorted(domain_emails.items(), key=lambda x: -len(x[1])):
            if len(emails_list) >= 2:
                suggestions.append({
                    "domain": domain,
                    "count": len(emails_list),
                    "sample_subjects": [e["subject"][:80] for e in emails_list[:5]],
                    "sample_sender": emails_list[0]["from"],
                })

        if suggestions:
            logger.info(f"[travel:discovery] Found {len(suggestions)} potential new providers")
        return suggestions
