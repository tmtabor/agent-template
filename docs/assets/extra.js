// A link to #recorded-run (the "See it run" line at the top of a pattern page) should show the
// recording, which is a closed block. The anchor sits just before the block; open the block it names.
function openRecordedRun() {
  if (location.hash !== "#recorded-run") return;
  const anchor = document.getElementById("recorded-run");
  if (!anchor) return;
  // Markdown wraps the empty anchor in a paragraph, so the block follows the paragraph.
  const holder = anchor.parentElement.tagName === "P" ? anchor.parentElement : anchor;
  const block = holder.nextElementSibling;
  if (block && block.tagName === "DETAILS") block.open = true;
}
// Material's instant navigation swaps pages without a load event, so listen to its observable.
if (typeof document$ !== "undefined") document$.subscribe(openRecordedRun);
else window.addEventListener("DOMContentLoaded", openRecordedRun);
window.addEventListener("hashchange", openRecordedRun);
