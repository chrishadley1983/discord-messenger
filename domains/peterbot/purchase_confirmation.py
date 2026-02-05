"""
Purchase Confirmation Handler

Handles the Discord confirmation flow for browser-based purchases.
Detects [PURCHASE_CONFIRMATION] blocks in responses and manages
the reaction-based approval process.
"""

import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from dataclasses import dataclass

import discord

# Confirmation settings
CONFIRM_EMOJI = "\u2705"  # Green checkmark
CANCEL_EMOJI = "\u274c"   # Red X
CONFIRMATION_TIMEOUT = 300  # 5 minutes


@dataclass
class PurchaseConfirmation:
    """Data from a purchase confirmation request."""

    item: str
    price: float
    domain: str
    delivery: Optional[str]
    session_id: str
    raw_data: dict


# Store pending confirmations: message_id -> confirmation data
pending_confirmations: dict[int, dict] = {}


def extract_confirmation_data(response: str) -> Optional[PurchaseConfirmation]:
    """
    Extract [PURCHASE_CONFIRMATION] block from a response.

    Args:
        response: The full response text

    Returns:
        PurchaseConfirmation if found, None otherwise
    """
    pattern = r'\[PURCHASE_CONFIRMATION\]\s*(\{.*?\})\s*\[/PURCHASE_CONFIRMATION\]'
    match = re.search(pattern, response, re.DOTALL)

    if not match:
        return None

    try:
        data = json.loads(match.group(1))
        return PurchaseConfirmation(
            item=data.get("item", "Unknown item"),
            price=float(data.get("price", 0)),
            domain=data.get("domain", "unknown"),
            delivery=data.get("delivery"),
            session_id=data.get("session_id", ""),
            raw_data=data,
        )
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        print(f"Error parsing purchase confirmation: {e}")
        return None


def remove_confirmation_block(response: str) -> str:
    """
    Remove the [PURCHASE_CONFIRMATION] block from response text.

    Args:
        response: The full response text

    Returns:
        Response with confirmation block removed
    """
    pattern = r'\[PURCHASE_CONFIRMATION\].*?\[/PURCHASE_CONFIRMATION\]\s*'
    return re.sub(pattern, '', response, flags=re.DOTALL).strip()


def has_confirmation_block(response: str) -> bool:
    """Check if response contains a purchase confirmation block."""
    return "[PURCHASE_CONFIRMATION]" in response and "[/PURCHASE_CONFIRMATION]" in response


async def send_confirmation_request(
    channel: discord.TextChannel,
    user_id: int,
    confirmation: PurchaseConfirmation,
) -> discord.Message:
    """
    Send a purchase confirmation embed to Discord.

    Args:
        channel: Discord channel to send to
        user_id: User ID who should confirm
        confirmation: Purchase confirmation data

    Returns:
        The sent Discord message
    """
    # Build embed
    embed = discord.Embed(
        title="Purchase Confirmation Required",
        color=discord.Color.orange(),
        timestamp=datetime.utcnow(),
    )

    embed.add_field(
        name="Item",
        value=confirmation.item,
        inline=False,
    )
    embed.add_field(
        name="Price",
        value=f"£{confirmation.price:.2f}",
        inline=True,
    )
    embed.add_field(
        name="Site",
        value=confirmation.domain.replace(".co.uk", "").title() + " UK",
        inline=True,
    )

    if confirmation.delivery:
        embed.add_field(
            name="Delivery",
            value=confirmation.delivery,
            inline=True,
        )

    embed.set_footer(
        text=f"React {CONFIRM_EMOJI} to confirm, {CANCEL_EMOJI} to cancel | Expires in 5 min"
    )

    # Send message
    msg = await channel.send(embed=embed)

    # Add reactions
    await msg.add_reaction(CONFIRM_EMOJI)
    await msg.add_reaction(CANCEL_EMOJI)

    # Store pending confirmation
    pending_confirmations[msg.id] = {
        "user_id": user_id,
        "confirmation": confirmation,
        "expires_at": datetime.utcnow() + timedelta(seconds=CONFIRMATION_TIMEOUT),
        "channel_id": channel.id,
    }

    return msg


async def wait_for_confirmation(
    bot: discord.Client,
    message: discord.Message,
    user_id: int,
    timeout: int = CONFIRMATION_TIMEOUT,
) -> Tuple[bool, str]:
    """
    Wait for user to react to confirmation message.

    Args:
        bot: Discord bot client
        message: The confirmation message
        user_id: User ID who should confirm
        timeout: Timeout in seconds

    Returns:
        Tuple of (confirmed: bool, reason: str)
    """

    def check(reaction: discord.Reaction, user: discord.User) -> bool:
        return (
            user.id == user_id
            and reaction.message.id == message.id
            and str(reaction.emoji) in [CONFIRM_EMOJI, CANCEL_EMOJI]
        )

    try:
        reaction, user = await bot.wait_for(
            'reaction_add',
            timeout=timeout,
            check=check,
        )

        # Clean up pending confirmation
        pending_confirmations.pop(message.id, None)

        # Update embed based on result
        embed = message.embeds[0] if message.embeds else None

        if str(reaction.emoji) == CONFIRM_EMOJI:
            if embed:
                embed.color = discord.Color.green()
                embed.set_footer(text="Confirmed - Processing purchase...")
                await message.edit(embed=embed)
            return True, "User confirmed purchase"

        else:
            if embed:
                embed.color = discord.Color.red()
                embed.set_footer(text="Cancelled by user")
                await message.edit(embed=embed)
            return False, "User cancelled purchase"

    except asyncio.TimeoutError:
        # Clean up pending confirmation
        pending_confirmations.pop(message.id, None)

        # Update embed to show expired
        embed = message.embeds[0] if message.embeds else None
        if embed:
            embed.color = discord.Color.greyple()
            embed.set_footer(text="Expired - No response within 5 minutes")
            try:
                await message.edit(embed=embed)
            except discord.errors.NotFound:
                pass

        return False, "Confirmation timeout - no response within 5 minutes"


async def handle_purchase_confirmation(
    bot: discord.Client,
    channel: discord.TextChannel,
    user_id: int,
    response: str,
) -> Tuple[str, Optional[str]]:
    """
    Handle a response that may contain a purchase confirmation.

    This is the main entry point for the confirmation flow.

    Args:
        bot: Discord bot client
        channel: Discord channel
        user_id: User who triggered the purchase
        response: Claude's response text

    Returns:
        Tuple of (cleaned_response, follow_up_instruction)
        - cleaned_response: Response with confirmation block removed
        - follow_up_instruction: Instruction to send back to Claude, or None
    """
    # Check for confirmation block
    if not has_confirmation_block(response):
        return response, None

    # Extract confirmation data
    confirmation = extract_confirmation_data(response)
    if not confirmation:
        # Malformed confirmation block - just return cleaned response
        return remove_confirmation_block(response), None

    # Remove the block from visible response
    cleaned_response = remove_confirmation_block(response)

    # Send confirmation request
    msg = await send_confirmation_request(channel, user_id, confirmation)

    # Wait for user reaction
    confirmed, reason = await wait_for_confirmation(bot, msg, user_id)

    # Generate follow-up instruction for Claude
    if confirmed:
        follow_up = (
            f"User confirmed purchase. Proceed with checkout and complete the order. "
            f"Session ID: {confirmation.session_id}"
        )
    else:
        follow_up = (
            f"User cancelled purchase. Reason: {reason}. "
            f"Close the browser session (session_id: {confirmation.session_id}) and inform the user."
        )

    return cleaned_response, follow_up


def get_pending_confirmation(message_id: int) -> Optional[dict]:
    """Get pending confirmation by message ID."""
    return pending_confirmations.get(message_id)


def cleanup_expired_confirmations():
    """Remove expired pending confirmations."""
    now = datetime.utcnow()
    expired = [
        msg_id for msg_id, data in pending_confirmations.items()
        if data["expires_at"] < now
    ]
    for msg_id in expired:
        pending_confirmations.pop(msg_id, None)


async def cancel_pending_confirmation(message_id: int) -> bool:
    """
    Cancel a pending confirmation.

    Args:
        message_id: The confirmation message ID

    Returns:
        True if cancelled, False if not found
    """
    data = pending_confirmations.pop(message_id, None)
    return data is not None
