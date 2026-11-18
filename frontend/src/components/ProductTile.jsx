/**
 * Visual stand-in for a product.
 *
 * The Online Retail dataset is invoice lines: there is no product photography
 * and no category column anywhere in it. Rather than source unrelated stock
 * photos and imply they are these SKUs, each product gets an icon tile keyed
 * to a category derived from its own name. Surfaces that show one carry a note
 * saying the category is derived.
 */
import { useState } from 'react'
import { categoryStyle } from '../lib/categories'
import { categoryImage } from '../lib/categoryImages'

const SIZES = {
  sm: { box: 'h-9 w-9 rounded-lg', icon: 16 },
  md: { box: 'h-12 w-12 rounded-xl', icon: 22 },
  lg: { box: 'h-16 w-16 rounded-2xl', icon: 30 },
  xl: { box: 'h-20 w-20 rounded-2xl', icon: 36 },
}

export function ProductTile({ category, size = 'md', className = '' }) {
  const { icon: Icon, hue, wash } = categoryStyle(category)
  const s = SIZES[size] || SIZES.md
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center ${s.box} ${className}`}
      style={{ background: wash, color: hue, border: `1px solid ${hue}22` }}
      title={category ? `${category} (derived from the product name)` : 'Uncategorised'}
      aria-hidden="true"
    >
      <Icon size={s.icon} strokeWidth={1.75} />
    </span>
  )
}

/**
 * Photograph of the product's category, falling back to the icon tile.
 *
 * The fallback is not decoration: `Uncategorised` products have no pinned
 * image on purpose (we could not classify them, so we do not imply we know
 * what they are), and a missing or broken file must degrade to an icon rather
 * than a broken-image glyph.
 *
 * The image is cropped with object-fit inside a fixed square so products of
 * wildly different source aspect ratios still line up in a grid.
 */
export function ProductPhoto({ category, size = 'md', className = '' }) {
  const [failed, setFailed] = useState(false)
  const image = categoryImage(category)
  const s = SIZES[size] || SIZES.md

  if (!image || failed) {
    return <ProductTile category={category} size={size} className={className} />
  }

  return (
    <span
      className={`relative inline-block shrink-0 overflow-hidden ${s.box} ${className}`}
      style={{ background: 'var(--surface-3)', border: '1px solid var(--border)' }}
      title={`${category} — representative photograph of the category, not this product`}
    >
      <img
        src={image.src}
        alt={image.alt}
        loading="lazy"
        decoding="async"
        onError={() => setFailed(true)}
        className="h-full w-full object-cover"
      />
    </span>
  )
}

/** The small print that must accompany a grid of product images. */
export function DerivedCategoryNote({ className = '' }) {
  return (
    <p className={`text-xs ${className}`} style={{ color: 'var(--text-muted)' }}>
      Photographs represent each product&apos;s category, which is parsed from its name —
      the dataset contains no product images or category column. Credits are on the{' '}
      <a className="link" href="/help">Documentation</a> page.
    </p>
  )
}

export function CategoryChip({ category }) {
  const { icon: Icon, hue } = categoryStyle(category)
  return (
    <span className="chip" style={{ color: hue }}>
      <Icon size={12} strokeWidth={2} />
      {category || 'Uncategorised'}
    </span>
  )
}
