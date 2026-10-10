/**
 * visual.js - a picture the tutor drew, as every front end shows it.
 *
 * The server sends the picture inline, in the `visual` message, after a `visual_pending`
 * message that says it is being drawn. Both are built here so the lab and the keynote stage
 * show them the same way, and so the one rule that matters is written once: the picture
 * comes with the tutor's description of it, which is what a screen reader reads.
 */

// A data URL of any other type is not a picture, whatever the message says.
const IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

/** The picture of a `visual` message as a data URL, or null when it is not a picture. */
export function visualSource(payload) {
  if (!payload?.image || !IMAGE_TYPES.has(payload.mime)) return null;
  return `data:${payload.mime};base64,${payload.image}`;
}

/** The picture, with its description under it. */
export function buildVisualFigure(src, description, className = "visual-card") {
  const figure = document.createElement("figure");
  figure.className = className;
  const image = document.createElement("img");
  image.setAttribute("src", src);
  image.setAttribute("alt", description || "A picture drawn by the tutor.");
  const caption = document.createElement("figcaption");
  // Read once, from the picture's alt: the same sentence twice is a screen reader stuttering.
  caption.setAttribute("aria-hidden", "true");
  caption.textContent = description || "";
  figure.appendChild(image);
  figure.appendChild(caption);
  return figure;
}

/** What stands in the picture's place while it is drawn: the tutor's own words, and motion. */
export function buildVisualPending(text, className = "visual-card pending") {
  const card = document.createElement("div");
  card.className = className;
  card.setAttribute("role", "status");
  const spinner = document.createElement("span");
  spinner.className = "visual-spinner";
  spinner.setAttribute("aria-hidden", "true");
  const note = document.createElement("span");
  note.className = "visual-pending-text";
  note.textContent = text || "Drawing…";
  card.appendChild(spinner);
  card.appendChild(note);
  return card;
}
