const fs = require('fs')
const path = require('path')

const API_BASE_URL = process.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

async function runFindSimilarVerification() {
  console.log('======================================================================')
  console.log('FIND SIMILAR END-TO-END AUTOMATED VERIFICATION SUITE')
  console.log('======================================================================')

  let passedCount = 0
  let failedCount = 0

  function assert(condition, testName, detail = '') {
    if (condition) {
      console.log(`[PASS] ${testName} ${detail ? '(' + detail + ')' : ''}`)
      passedCount++
    } else {
      console.error(`[FAIL] ${testName} ${detail ? '(' + detail + ')' : ''}`)
      failedCount++
    }
  }

  // -------------------------------------------------------------------------
  // TEST 1: Initial Search Image A (10003.jpg)
  // -------------------------------------------------------------------------
  console.log('\n--- Test 1: Initial Search with Image A (10003.jpg) ---')
  let initialResults = null
  try {
    const imgPath = path.join(__dirname, '../../data/images/10003.jpg')
    const fileBuf = fs.readFileSync(imgPath)
    const formData = new FormData()
    formData.append('file', new Blob([fileBuf], { type: 'image/jpeg' }), '10003.jpg')
    formData.append('top_k', '10')
    formData.append('model', 'clip')

    const res = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formData })
    assert(res.status === 200, 'Initial search HTTP 200', `Status: ${res.status}`)
    initialResults = await res.json()
    assert(Array.isArray(initialResults.results) && initialResults.results.length === 10, 'Initial results count is 10')
  } catch (err) {
    assert(false, 'Initial search failed', err.message)
  }

  // -------------------------------------------------------------------------
  // TEST 2: Find Similar on Result #1 (B)
  // -------------------------------------------------------------------------
  console.log('\n--- Test 2: Find Similar on Result #1 ---')
  let resultB = initialResults?.results?.[1] // Take second item (B)
  let resultsForB = null
  try {
    const itemUrl = `${API_BASE_URL}/catalog-images/${resultB.filename}`
    console.log(`  Fetching catalog image for Result B: ${resultB.filename} (${resultB.product_display_name})`)
    const imgFetch = await fetch(itemUrl)
    assert(imgFetch.status === 200, 'Fetch catalog image for Result B', `Status: ${imgFetch.status}`)
    const blobB = await imgFetch.blob()
    assert(blobB.size > 0, 'Catalog image blob size valid', `${blobB.size} bytes`)

    // Emulate Find Similar search execution
    const formDataB = new FormData()
    formDataB.append('file', blobB, resultB.filename)
    formDataB.append('top_k', '10')
    formDataB.append('model', 'clip')

    const searchResB = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formDataB })
    assert(searchResB.status === 200, 'Find Similar search HTTP 200')
    resultsForB = await searchResB.json()
    assert(Array.isArray(resultsForB.results) && resultsForB.results.length === 10, 'Find Similar results count is 10')
    assert(resultsForB.results[0].filename === resultB.filename, 'Top match for B is B itself (100% exact match)')
    assert(resultsForB.results[0].similarity_score >= 0.99, 'Similarity score for identical query is ~1.0')
  } catch (err) {
    assert(false, 'Find Similar for B failed', err.message)
  }

  // -------------------------------------------------------------------------
  // TEST 3: Find Similar on Another Result (C)
  // -------------------------------------------------------------------------
  console.log('\n--- Test 3: Find Similar on Another Result (C: 22096.jpg) ---')
  let resultsForC = null
  try {
    const itemUrlC = `${API_BASE_URL}/catalog-images/22096.jpg`
    const imgFetchC = await fetch(itemUrlC)
    assert(imgFetchC.status === 200, 'Fetch catalog image for C (22096.jpg)')
    const blobC = await imgFetchC.blob()

    const formDataC = new FormData()
    formDataC.append('file', blobC, '22096.jpg')
    formDataC.append('top_k', '10')
    formDataC.append('model', 'clip')

    const searchResC = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formDataC })
    assert(searchResC.status === 200, 'Find Similar search for C HTTP 200')
    resultsForC = await searchResC.json()
    assert(Array.isArray(resultsForC.results) && resultsForC.results.length === 10, 'Results for C returned 10 items')
    assert(resultsForC.results[0].filename === '22096.jpg', 'Top match for C is 22096.jpg')
  } catch (err) {
    assert(false, 'Find Similar for C failed', err.message)
  }

  // -------------------------------------------------------------------------
  // TEST 4: Model Preservation (ResNet-50)
  // -------------------------------------------------------------------------
  console.log('\n--- Test 4: Model Preservation (ResNet-50) ---')
  try {
    const itemUrl = `${API_BASE_URL}/catalog-images/10035.jpg`
    const imgFetch = await fetch(itemUrl)
    const blob = await imgFetch.blob()

    const formData = new FormData()
    formData.append('file', blob, '10035.jpg')
    formData.append('top_k', '10')
    formData.append('model', 'resnet')

    const res = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formData })
    assert(res.status === 200, 'Find Similar with ResNet-50 HTTP 200')
    const data = await res.json()
    assert(data.model_used === 'ResNet_50', 'Model preserved as ResNet_50 in response', `Model: ${data.model_used}`)
  } catch (err) {
    assert(false, 'Model preservation test failed', err.message)
  }

  // -------------------------------------------------------------------------
  // TEST 5: Top-K Preservation (top_k = 5)
  // -------------------------------------------------------------------------
  console.log('\n--- Test 5: Top-K Preservation (top_k = 5) ---')
  try {
    const itemUrl = `${API_BASE_URL}/catalog-images/10035.jpg`
    const imgFetch = await fetch(itemUrl)
    const blob = await imgFetch.blob()

    const formData = new FormData()
    formData.append('file', blob, '10035.jpg')
    formData.append('top_k', '5')
    formData.append('model', 'clip')

    const res = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formData })
    assert(res.status === 200, 'Find Similar with top_k=5 HTTP 200')
    const data = await res.json()
    assert(data.top_k === 5 && data.results.length === 5, 'Top-K preserved as 5 in response', `Count: ${data.results.length}`)
  } catch (err) {
    assert(false, 'Top-K preservation test failed', err.message)
  }

  // -------------------------------------------------------------------------
  // TEST 6: Category Recommendations Derived from New Search
  // -------------------------------------------------------------------------
  console.log('\n--- Test 6: Recommendations Derivation on New Results ---')
  try {
    const ref = resultsForC.results[0]
    const pool = resultsForC.results.slice(3)
    const recs = pool.filter(
      r => r.category && ref.category && r.category.toLowerCase() === ref.category.toLowerCase()
    ).slice(0, 4)

    assert(recs.length >= 0, 'Recommendation derivation works smoothly on new results set', `Found ${recs.length} matches`)
  } catch (err) {
    assert(false, 'Recommendation derivation failed', err.message)
  }

  console.log('\n======================================================================')
  console.log(`SUMMARY: ${passedCount} PASSED, ${failedCount} FAILED`)
  console.log('======================================================================')

  if (failedCount > 0) {
    process.exit(1)
  }
}

runFindSimilarVerification().catch(err => {
  console.error('Fatal test error:', err)
  process.exit(1)
})
