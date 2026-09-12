import React, { useState, useEffect } from 'react'
import { getCatalogImageUrl, fetchTopCategories, fetchCategoryProducts } from '../services/searchApi'

const DEFAULT_TOP_CATEGORIES = [
  {
    category_name: 'Tshirts',
    master_category: 'Apparel',
    item_count: 7023,
    sample_filename: '10003.jpg',
    sample_image_url: '/catalog-images/10003.jpg',
    icon: '👕',
  },
  {
    category_name: 'Shirts',
    master_category: 'Apparel',
    item_count: 3186,
    sample_filename: '37783.jpg',
    sample_image_url: '/catalog-images/37783.jpg',
    icon: '👔',
  },
  {
    category_name: 'Casual Shoes',
    master_category: 'Footwear',
    item_count: 2828,
    sample_filename: '22096.jpg',
    sample_image_url: '/catalog-images/22096.jpg',
    icon: '👟',
  },
  {
    category_name: 'Watches',
    master_category: 'Accessories',
    item_count: 2531,
    sample_filename: '45225.jpg',
    sample_image_url: '/catalog-images/45225.jpg',
    icon: '⌚',
  },
  {
    category_name: 'Sports Shoes',
    master_category: 'Footwear',
    item_count: 2024,
    sample_filename: '10035.jpg',
    sample_image_url: '/catalog-images/10035.jpg',
    icon: '🏃',
  },
  {
    category_name: 'Kurtas',
    master_category: 'Apparel',
    item_count: 1821,
    sample_filename: '54587.jpg',
    sample_image_url: '/catalog-images/54587.jpg',
    icon: '👗',
  },
  {
    category_name: 'Tops',
    master_category: 'Apparel',
    item_count: 1750,
    sample_filename: '10324.jpg',
    sample_image_url: '/catalog-images/10324.jpg',
    icon: '👚',
  },
  {
    category_name: 'Handbags',
    master_category: 'Accessories',
    item_count: 1743,
    sample_filename: '6557.jpg',
    sample_image_url: '/catalog-images/6557.jpg',
    icon: '👜',
  },
]

export default function SampleQueries({ onSelectCategoryData, onSelectSample, loading }) {
  const [categories, setCategories] = useState(DEFAULT_TOP_CATEGORIES)
  const [activeCategoryName, setActiveCategoryName] = useState(null)

  useEffect(() => {
    fetchTopCategories(8)
      .then((data) => {
        if (data && Array.isArray(data.categories) && data.categories.length > 0) {
          const iconMap = {
            Tshirts: '👕',
            Shirts: '👔',
            'Casual Shoes': '👟',
            Watches: '⌚',
            'Sports Shoes': '🏃',
            Kurtas: '👗',
            Tops: '👚',
            Handbags: '👜',
            Heels: '👠',
            Sunglasses: '🕶️',
          }
          const merged = data.categories.map((c) => ({
            ...c,
            icon: iconMap[c.category_name] || '🛍️',
          }))
          setCategories(merged)
        }
      })
      .catch((err) => {
        console.warn('Using default top categories:', err)
      })
  }, [])

  const handleCategoryClick = async (cat) => {
    if (loading) return
    setActiveCategoryName(cat.category_name)

    try {
      const sampleFilename = cat.sample_filename || (cat.sample_image_url ? cat.sample_image_url.split('/').pop() : 'query.jpg')
      const sampleFullUrl = getCatalogImageUrl(cat.sample_image_url || `/catalog-images/${sampleFilename}`)
      
      if (onSelectSample) {
        await onSelectSample(sampleFilename, sampleFullUrl, cat.category_name)
      }
    } catch (err) {
      console.error('Failed to search quick select sample:', err)
    } finally {
      setActiveCategoryName(null)
    }
  }

  return (
    <div className="sample-queries-container">
      <div className="sample-header">
        <span className="sample-badge">⚡ Quick Select Categories</span>
        <span className="sample-heading">
          Click any category image to search for visually and semantically similar products in real time:
        </span>
      </div>

      <div className="sample-grid">
        {categories.map((cat) => {
          const isThisLoading = loading && activeCategoryName === cat.category_name
          const imgUrl = getCatalogImageUrl(cat.sample_image_url || `/catalog-images/${cat.sample_filename}`)
          return (
            <button
              key={cat.category_name}
              className={`sample-card-btn ${isThisLoading ? 'loading' : ''}`}
              onClick={() => handleCategoryClick(cat)}
              disabled={loading}
              title={`Search products visually similar to ${cat.category_name}`}
            >
              <div className="sample-img-box">
                <img
                  src={imgUrl}
                  alt={cat.category_name}
                  loading="lazy"
                  onError={(e) => {
                    e.target.style.display = 'none'
                  }}
                />
                <span className="sample-category-icon">{cat.icon}</span>
              </div>
              <div className="sample-meta">
                <span className="sample-title">{cat.category_name}</span>
                <span className="sample-cat">
                  {cat.item_count ? `${cat.item_count.toLocaleString()} items` : cat.master_category}
                </span>
              </div>
              {isThisLoading && (
                <div className="preset-spinner-overlay">
                  <span className="spinner-inline"></span>
                </div>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
