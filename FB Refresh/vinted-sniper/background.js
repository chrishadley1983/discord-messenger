/**
 * Vinted Sniper — Background Service Worker
 * Fetches images (CORS-free via host_permissions on *.vinted.net)
 * and calls Gemini Vision API to identify Lego set numbers
 */

const GEMINI_KEY = 'AIzaSyDTU12qSQ8PE_xMEuZkmtWIoFq8s7BHHy4';
const GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent';

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'identifyImage') {
    handleIdentify(msg.imageUrl, msg.listingId)
      .then(result => sendResponse(result))
      .catch(err => sendResponse({ error: err.message }));
    return true;
  }
});

async function handleIdentify(imageUrl, listingId) {
  if (!imageUrl || !imageUrl.startsWith('https')) {
    return { setNum: null, error: 'Invalid image URL' };
  }

  try {
    // Step 1: Fetch the image from Vinted CDN (no CORS in background with host_permissions)
    const imgRes = await fetch(imageUrl);
    if (!imgRes.ok) {
      return { setNum: null, error: `Image fetch failed: ${imgRes.status}` };
    }

    const blob = await imgRes.blob();
    const mimeType = blob.type || 'image/jpeg';

    // Convert blob to base64
    const arrayBuffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    const base64 = btoa(binary);

    // Step 2: Call Gemini Vision
    const res = await fetch(`${GEMINI_URL}?key=${GEMINI_KEY}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{
          parts: [
            {
              inline_data: {
                mime_type: mimeType,
                data: base64
              }
            },
            {
              text: 'This is a photo from a LEGO product listing on Vinted. What is the LEGO set number? Look for a 4-6 digit number printed on the box, on labels, or visible on the product. Reply with ONLY the set number (e.g. 75341) and nothing else. If you cannot identify a specific set number, reply with only the word UNKNOWN.'
            }
          ]
        }]
      })
    });

    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      return { setNum: null, error: `Gemini ${res.status}: ${errText.substring(0, 150)}` };
    }

    const data = await res.json();
    const text = data.candidates?.[0]?.content?.parts?.[0]?.text?.trim() || '';

    const numMatch = text.match(/\b(\d{4,6})\b/);
    if (numMatch && text.toUpperCase() !== 'UNKNOWN') {
      return { setNum: numMatch[1], raw: text };
    } else {
      return { setNum: null, raw: text };
    }
  } catch (e) {
    return { setNum: null, error: e.message };
  }
}
