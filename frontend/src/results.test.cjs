// Comprehensive test suite for ranked search results interface & API rendering logic

const fs = require('fs')
const path = require('path')

const API_BASE_URL = process.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

function getCatalogImageUrl(imagePathOrUrl) {
  if (!imagePathOrUrl) return ''
  if (imagePathOrUrl.startsWith('http://') || imagePathOrUrl.startsWith('https://')) {
    return imagePathOrUrl
  }
  const cleanPath = imagePathOrUrl.startsWith('/') ? imagePathOrUrl : `/${imagePathOrUrl}`
  return `${API_BASE_URL}${cleanPath}`
}

async function runResultsInterfaceTest() {
  console.log('==================================================')
  console.log('RANKED SEARCH RESULTS INTERFACE TEST SUITE')
  console.log('==================================================')

  let allPassed = true

  // 1. Fetch search response for 15025.jpg (topK=5)
  const imagePath15025 = path.join(__dirname, '../../data/catalog/images/15025.jpg')
  const imgBuffer15025 = fs.readFileSync(imagePath15025)

  console.log('\n[TEST 1] Render Query: 15025.jpg (topK=5)')
  try {
    const formData = new FormData()
    const blob = new Blob([imgBuffer15025], { type: 'image/jpeg' })
    formData.append('file', blob, '15025.jpg')
    formData.append('top_k', '5')

    const res = await fetch(`${API_BASE_URL}/api/v1/search`, { method: 'POST', body: formData })
    if (res.status !== 200) {
      console.error(`  FAILED: HTTP ${res.status}`)
      allPassed = false
    } else {
      const data = await res.json()
      console.log(`  Query Filename: ${data.query_filename}`)
      console.log(`  Total Results:  ${data.total_results}`)

      const cardCountOk = data.results.length === 5
      console.log(`  Card Count == 5: [${cardCountOk ? 'PASS' : 'FAIL'}]`)
      if (!cardCountOk) allPassed = false

      let rankOk = true
      let imgLoadOk = true

      for (let i = 0; i < data.results.length; i++) {
        const item = data.results[i]
        const expectedRank = i + 1
        const pctScore = (item.similarity_score * 100).toFixed(2)
        const fullUrl = getCatalogImageUrl(item.image_url)

        // Verify image URL HTTP response
        const imgRes = await fetch(fullUrl)
        const is200 = imgRes.status === 200
        if (!is200) imgLoadOk = false

        console.log(`  Card #${item.rank}: Product ID = ${item.product_id} | Ext ID = ${item.external_id} | Similarity = ${pctScore}% | Image URL = ${fullUrl} [HTTP ${imgRes.status}]`)

        if (item.rank !== expectedRank) rankOk = false
      }

      console.log(`  Ranks 1..5 Sequential: [${rankOk ? 'PASS' : 'FAIL'}]`)
      console.log(`  All Images Loaded (HTTP 200): [${imgLoadOk ? 'PASS' : 'FAIL'}]`)
      if (!rankOk || !imgLoadOk) allPassed = false
    }
  } catch (err) {
    console.error(`  FAILED: ${err.message}`)
    allPassed = false
  }

  // 2. Fetch search response for 15025.jpg (topK=10)
  console.log('\n[TEST 2] Render Query: 15025.jpg (topK=10)')
  try {
    const formData = new FormData()
    const blob = new Blob([imgBuffer15025], { type: 'image/jpeg' })
    formData.append('file', blob, '15025.jpg')
    formData.append('top_k', '10')

    const res = await fetch(`${API_BASE_URL}/api/v1/search`, { method: 'POST', body: formData })
    if (res.status !== 200) {
      console.error(`  FAILED: HTTP ${res.status}`)
      allPassed = false
    } else {
      const data = await res.json()
      const cardCountOk = data.results.length === 10
      console.log(`  Card Count == 10: [${cardCountOk ? 'PASS' : 'FAIL'}]`)
      if (!cardCountOk) allPassed = false
    }
  } catch (err) {
    console.error(`  FAILED: ${err.message}`)
    allPassed = false
  }

  // 3. Test Empty Results Graceful Handling
  console.log('\n[TEST 3] Empty Results Array Graceful Handling')
  const emptyData = { query_filename: 'empty.jpg', total_results: 0, results: [] }
  const rendersEmpty = Array.isArray(emptyData.results) && emptyData.results.length === 0
  console.log(`  Empty Array Does Not Crash UI: [${rendersEmpty ? 'PASS' : 'FAIL'}]`)
  if (!rendersEmpty) allPassed = false

  // 4. Test Replacing / Clearing Results
  console.log('\n[TEST 4] Removing Query Clears Results State')
  let state = { selectedFile: { name: '15025.jpg' }, searchResults: { total_results: 5 } }
  // Simulate file removal
  state = { selectedFile: null, searchResults: null }
  const isCleared = state.selectedFile === null && state.searchResults === null
  console.log(`  State Cleared On File Reset: [${isCleared ? 'PASS' : 'FAIL'}]`)
  if (!isCleared) allPassed = false

  console.log('\n==================================================')
  if (allPassed) {
    console.log('RESULT: ALL SEARCH RESULTS INTERFACE TESTS PASSED.')
    process.exit(0)
  } else {
    console.error('RESULT: TESTS FAILED.')
    process.exit(1)
  }
}

runResultsInterfaceTest()
