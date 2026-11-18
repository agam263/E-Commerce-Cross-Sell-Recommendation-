/**
 * Presentation for the derived product categories.
 *
 * The category itself comes from the API (`crosssell.service.categories`),
 * which parses it out of the product name. This file only decides how to draw
 * it: an icon and a hue.
 *
 * The dataset has no product photography and no category column, so these
 * tiles are explicitly a reading aid derived from the name -- never a claim
 * that this is a picture of the SKU, and never a retailer taxonomy. Every
 * surface that shows one says so.
 */
import {
  Box,
  Flame,
  Gamepad2,
  Gem,
  House,
  NotebookPen,
  Package,
  PartyPopper,
  TreePine,
  Shirt,
  ShoppingBag,
  Sprout,
  Utensils,
} from 'lucide-react'

/** Hues are drawn from the token palette so tiles stay inside the design system. */
export const CATEGORY_STYLES = {
  'Christmas & Seasonal': { icon: TreePine, hue: 'var(--bad)', wash: 'var(--bad-weak)' },
  'Party & Celebration': { icon: PartyPopper, hue: 'var(--series-2)', wash: 'var(--warn-weak)' },
  'Bags & Totes': { icon: ShoppingBag, hue: 'var(--series-1)', wash: 'var(--accent-weak)' },
  'Candles & Lighting': { icon: Flame, hue: 'var(--warn)', wash: 'var(--warn-weak)' },
  'Kitchen & Dining': { icon: Utensils, hue: 'var(--series-3)', wash: 'var(--good-weak)' },
  'Storage & Containers': { icon: Package, hue: 'var(--text-secondary)', wash: 'var(--surface-3)' },
  'Stationery & Paper': { icon: NotebookPen, hue: 'var(--series-1)', wash: 'var(--accent-weak)' },
  'Jewellery & Accessories': { icon: Gem, hue: 'var(--accent)', wash: 'var(--accent-weak)' },
  'Toys & Games': { icon: Gamepad2, hue: 'var(--series-2)', wash: 'var(--warn-weak)' },
  'Garden & Outdoor': { icon: Sprout, hue: 'var(--series-3)', wash: 'var(--good-weak)' },
  'Home Decor': { icon: House, hue: 'var(--series-1)', wash: 'var(--accent-weak)' },
  'Textiles & Soft Goods': { icon: Shirt, hue: 'var(--accent)', wash: 'var(--accent-weak)' },
}

const FALLBACK = { icon: Box, hue: 'var(--text-muted)', wash: 'var(--surface-3)' }

export function categoryStyle(category) {
  return CATEGORY_STYLES[category] || FALLBACK
}

export const CATEGORY_NAMES = Object.keys(CATEGORY_STYLES)
