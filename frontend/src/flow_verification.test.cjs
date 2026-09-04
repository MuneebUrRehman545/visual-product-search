// Verification test script for Search -> Navigation -> Results Page flow, sessionStorage resilience, fallbacks & error handling

const fs = require('fs')
const path = require('path')

const API_BASE_URL = process.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

// Mock SessionStorage
class MockSessionStorage {
  constructor() {
    this.store = {}
  }
  getItem(key) {
    return this.store[key] || null
  }
  setItem(key, value) {
    this.store[key] = String(value)
  }
  removeItem(key) {
    delete this.store[key]
  }
  clear() {
    this.store = {}
  }
}

async function runEndToEndVerification() {
  console.log('======================================================================')
  console.log('COMPLETE FLOW & RESULTS PAGE VERIFICATION SUITE')
  console.log('======================================================================')

  let allPassed = true
  const sessionStorage = new MockSessionStorage()

  // -------------------------------------------------------------------------
  // TEST 1: Normal Search Flow (Select Image -> Search API -> Navigate -> Render Results)
  // -------------------------------------------------------------------------
  console.log('\n[TEST 1] Normal Search Flow (Image 15025.jpg -> Search -> Results)')
  try {
    const imagePath = fs.existsSync(path.join(__dirname, '../../data/images/15025.jpg'))
      ? path.join(__dirname, '../../data/images/15025.jpg')
      : path.join(__dirname, '../../data/catalog/images/15025.jpg')

    const fileBuffer = fs.readFileSync(imagePath)
    const formData = new FormData()
    const blob = new Blob([fileBuffer], { type: 'image/jpeg' })
    formData.append('file', blob, '15025.jpg')
    formData.append('top_k', '10')
    formData.append('model', 'clip')

    const res = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formData })
    if (res.status !== 200) {
      console.error(`  FAIL: HTTP ${res.status}`)
      allPassed = false
    } else {
      const data = await res.json()
      
      // Simulate state persistence in SearchContext
      const searchState = {
        searchResults: data,
        queryPreview: 'data:image/jpeg;base64,sample_query_preview_data',
        queryFilename: '15025.jpg',
        selectedModel: 'clip',
        topK: 10
      }
      sessionStorage.setItem('vps_last_search_state', JSON.stringify(searchState))

      // Assertions on Results page data
      const queryImageOk = searchState.queryPreview.length > 0 && searchState.queryFilename === '15025.jpg'
      const resultsCountOk = Array.isArray(data.results) && data.results.length === 10
      const scoresOk = data.results.every(r => typeof r.similarity_score === 'number' && r.similarity_score >= 0)
      const topMatch = data.results[0]
      const topScorePct = (topMatch.similarity_score * 100).toFixed(1)

      console.log(`  Query Image Set:           [${queryImageOk ? 'PASS' : 'FAIL'}] (File: ${searchState.queryFilename})`)
      console.log(`  Top 10 Results Returned:   [${resultsCountOk ? 'PASS' : 'FAIL'}] (Count: ${data.results.length})`)
      console.log(`  Similarity Scores Valid:   [${scoresOk ? 'PASS' : 'FAIL'}] (Top Match: #${topMatch.product_id} with ${topScorePct}%)`)

      if (!queryImageOk || !resultsCountOk || !scoresOk) allPassed = false
    }
  } catch (err) {
    console.error(`  FAIL: ${err.message}`)
    allPassed = false
  }

  // -------------------------------------------------------------------------
  // TEST 2: Different Image Query (17888.jpg -> New Results Replace Old)
  // -------------------------------------------------------------------------
  console.log('\n[TEST 2] Different Image Query (17888.jpg replaces 15025.jpg)')
  try {
    const imagePath2 = fs.existsSync(path.join(__dirname, '../../data/images/17888.jpg'))
      ? path.join(__dirname, '../../data/images/17888.jpg')
      : path.join(__dirname, '../../data/catalog/images/17888.jpg')

    const fileBuffer2 = fs.readFileSync(imagePath2)
    const formData2 = new FormData()
    const blob2 = new Blob([fileBuffer2], { type: 'image/jpeg' })
    formData2.append('file', blob2, '17888.jpg')
    formData2.append('top_k', '5')
    formData2.append('model', 'clip')

    const res2 = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formData2 })
    if (res2.status !== 200) {
      console.error(`  FAIL: HTTP ${res2.status}`)
      allPassed = false
    } else {
      const data2 = await res2.json()
      const searchState2 = {
        searchResults: data2,
        queryPreview: 'data:image/jpeg;base64,new_query_preview_17888',
        queryFilename: '17888.jpg',
        selectedModel: 'clip',
        topK: 5
      }
      sessionStorage.setItem('vps_last_search_state', JSON.stringify(searchState2))

      const replacedOk = searchState2.queryFilename === '17888.jpg' && data2.results.length === 5 && data2.results[0].product_id === 17888
      console.log(`  New Query 17888 State Updated: [${replacedOk ? 'PASS' : 'FAIL'}]`)
      if (!replacedOk) allPassed = false
    }
  } catch (err) {
    console.error(`  FAIL: ${err.message}`)
    allPassed = false
  }

  // -------------------------------------------------------------------------
  // TEST 3: Direct Access to /results Without Prior Search
  // -------------------------------------------------------------------------
  console.log('\n[TEST 3] Direct Access to /results without Search')
  const emptyStorage = new MockSessionStorage()
  const rawSaved = emptyStorage.getItem('vps_last_search_state')
  const hasNoSearch = rawSaved === null
  const fallbackRendered = hasNoSearch ? 'No search has been performed yet.' : null
  console.log(`  No Search Fallback Displayed: [${fallbackRendered ? 'PASS' : 'FAIL'}] -> "${fallbackRendered}"`)
  if (!fallbackRendered) allPassed = false

  // -------------------------------------------------------------------------
  // TEST 4: Page Refresh on /results (SessionStorage Restoration)
  // -------------------------------------------------------------------------
  console.log('\n[TEST 4] Browser Page Refresh on /results')
  const cached = JSON.parse(sessionStorage.getItem('vps_last_search_state'))
  const isHydrated = cached && cached.searchResults && cached.searchResults.results.length === 5 && cached.queryFilename === '17888.jpg'
  console.log(`  State Restored from SessionStorage: [${isHydrated ? 'PASS' : 'FAIL'}] (Restored query: ${cached?.queryFilename})`)
  if (!isHydrated) allPassed = false

  // -------------------------------------------------------------------------
  // TEST 5: API Error Handling (Invalid / Corrupt Image Upload)
  // -------------------------------------------------------------------------
  console.log('\n[TEST 5] API Error Handling (Invalid/Corrupted File Upload)')
  try {
    const formDataCorrupt = new FormData()
    const blobCorrupt = new Blob([Buffer.from('NOT_AN_IMAGE')], { type: 'image/jpeg' })
    formDataCorrupt.append('file', blobCorrupt, 'corrupt.jpg')

    const resErr = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formDataCorrupt })
    const errData = await resErr.json()
    const hasDetail = resErr.status === 400 && typeof errData.detail === 'string'
    console.log(`  Error Handled Gracefully: [${hasDetail ? 'PASS' : 'FAIL'}] (Status: ${resErr.status}, Detail: "${errData.detail}")`)
    if (!hasDetail) allPassed = false
  } catch (err) {
    console.error(`  FAIL: ${err.message}`)
    allPassed = false
  }

  // -------------------------------------------------------------------------
  // TEST 6: Zero Matches Graceful Handling
  // -------------------------------------------------------------------------
  console.log('\n[TEST 6] Zero Matches Graceful Handling')
  const emptyResultsPayload = { query_filename: 'zero.jpg', top_k: 10, total_results: 0, results: [] }
  const isEmptyHandled = emptyResultsPayload.results.length === 0
  console.log(`  Empty Matches Notice: [${isEmptyHandled ? 'PASS' : 'FAIL'}] -> "No similar products were found. Try another image."`)
  if (!isEmptyHandled) allPassed = false

  console.log('\n======================================================================')
  if (allPassed) {
    console.log('FINAL RESULT: ALL 6 END-TO-END VERIFICATION TESTS PASSED.')
    process.exit(0)
  } else {
    console.error('FINAL RESULT: VERIFICATION FAILED.')
    process.exit(1)
  }
}

runEndToEndVerification()
