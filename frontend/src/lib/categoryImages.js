/**
 * Representative photography per derived product category.
 *
 * What these images are, and are not
 * ----------------------------------
 * The Online Retail dataset has no product photography and no image URLs, so
 * there is no photograph of StockCode 85123A to show. Searching a photo library
 * for the real SKU names returns nothing: "white hanging heart t-light holder",
 * "jumbo bag red retrospot" and "regency cakestand 3 tier" each return zero
 * results, and loosening the query returns the wrong object.
 *
 * So each product shows a photograph of its *category*, chosen once by hand.
 * Every surface that renders one says so, and the alt text says so too. This is
 * a reading aid, not a claim that the picture is the SKU.
 *
 * The files are vendored into frontend/public/category-images/ by
 * scripts/fetch_category_images.py, so nothing is fetched from an external host
 * while anyone is using the dashboard.
 */
import attribution from '../../public/category-images/attribution.json'

const BASE = '/category-images'

/** Categories with no pinned photograph fall through to the icon tile. */
export function categoryImage(category) {
  const entry = attribution[category]
  if (!entry) return null
  return {
    src: `${BASE}/${entry.file}`,
    alt: `Representative photograph of the ${category} category — not a photograph of this product`,
    credit: entry,
  }
}

export function hasCategoryImage(category) {
  return Boolean(attribution[category])
}

/** Every credit, for the attribution block the BY/BY-SA licences require. */
export const IMAGE_CREDITS = Object.entries(attribution)
  .map(([category, entry]) => ({ category, ...entry }))
  .sort((a, b) => a.category.localeCompare(b.category))
