/** Fixed places are used only for reproducible baseline regression cases. */
async function selectSamplePlace(page, label, value) {
  const select = page.getByLabel(`${label}: địa điểm mẫu`, { exact: true });
  const details = select.locator("..");
  if ((await details.getAttribute("open")) === null)
    await details.locator("summary").click();
  await select.selectOption(String(value));
  await details.locator("summary").click();
}

module.exports = { selectSamplePlace };
