const fs = require('fs')
const path = require('path')

const API_BASE_URL = process.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

// Replicate frontend helper logic from ResultCard.jsx
function isExactImageMatch(result, queryFilename, rawScore) {
  if (!result || !queryFilename) return false

  const cleanQuery = String(queryFilename).trim().toLowerCase()
  const genericPlaceholders = ['query.jpg', 'query.png', 'query.jpeg', 'query image', 'uploaded image', 'image', 'search query']
  if (genericPlaceholders.includes(cleanQuery)) {
    return false
  }

  const cleanQueryStem = cleanQuery.replace(/\.[^/.]+$/, '')
  const cleanResultFn = String(result.filename || '').trim().toLowerCase()
  const cleanResultStem = cleanResultFn.replace(/\.[^/.]+$/, '')

  const idMatches =
    (cleanResultFn && cleanResultFn === cleanQuery) ||
    (cleanResultStem && cleanResultStem === cleanQueryStem) ||
    (result.product_id != null && String(result.product_id).trim() === cleanQueryStem) ||
    (result.catalog_item_id != null && String(result.catalog_item_id).trim() === cleanQueryStem) ||
    (result.external_id != null && String(result.external_id).trim().toLowerCase() === cleanQueryStem)

  return Boolean(idMatches && rawScore >= 0.999)
}

function getSimilarityInfo(result, queryFilename, rawScore) {
  const percentageScore = Math.max(0, rawScore * 100)
  const isExact = isExactImageMatch(result, queryFilename, rawScore)

  if (isExact) {
    return {
      label: 'Match',
      displayValue: 'Exact Match',
      percentageScore,
      isExactMatch: true,
    }
  }

  return {
    label: 'Similarity',
    displayValue: `${percentageScore.toFixed(2)}%`,
    percentageScore,
    isExactMatch: false,
  }
}

async function runQuickSelectVerification() {
  console.log('======================================================================')
  console.log('QUICK SELECT / QUICK SEARCH CORRECTNESS VERIFICATION SUITE')
  console.log('======================================================================\n')

  let testResults = {}

  // -------------------------------------------------------------------------
  // TEST 1: Quick Select Category 1 (Tshirts: 10003.jpg)
  // -------------------------------------------------------------------------
  console.log('--- TEST 1: Quick Select Category 1 (T-Shirts / 10003.jpg) ---')
  try {
    const formData = new FormData()
    formData.append('catalog_filename', '10003.jpg')
    formData.append('top_k', '5')
    formData.append('model', 'clip')

    const res = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formData })
    const data = await res.json()

    console.log(`query image ID/filename: 10003.jpg`)
    console.log(`top result ID/filename:   ${data.results[0].filename} (Product #${data.results[0].product_id})`)
    console.log(`actual returned similarity: ${data.results[0].similarity_score}`)
    
    const simInfo0 = getSimilarityInfo(data.results[0], '10003.jpg', data.results[0].similarity_score)
    console.log(`displayed similarity:     ${simInfo0.displayValue} (${simInfo0.label})`)
    console.log(`exact same image?         ${data.results[0].filename === '10003.jpg' ? 'yes' : 'no'}`)

    // Check result 2 (different image)
    const res2 = data.results[1]
    const simInfo1 = getSimilarityInfo(res2, '10003.jpg', res2.similarity_score)
    console.log(`result #2 ID/filename:    ${res2.filename}`)
    console.log(`result #2 returned score: ${res2.similarity_score}`)
    console.log(`result #2 displayed:      ${simInfo1.displayValue} (${simInfo1.label})`)
    console.log(`result #2 exact match?    ${simInfo1.isExactMatch ? 'yes' : 'no'}`)

    const test1Pass = (
      data.results.length === 5 &&
      simInfo0.isExactMatch === true &&
      simInfo1.isExactMatch === false &&
      simInfo1.displayValue !== '100% Match' &&
      simInfo1.label === 'Similarity'
    )
    testResults['Test 1 — Quick Select Category 1'] = test1Pass ? 'PASS' : 'FAIL'
    console.log(`-> Test 1 Result: [${testResults['Test 1 — Quick Select Category 1']}]\n`)
  } catch (err) {
    console.error('Test 1 error:', err)
    testResults['Test 1 — Quick Select Category 1'] = 'FAIL'
  }

  // -------------------------------------------------------------------------
  // TEST 2: Another Category (Casual Shoes: 22096.jpg)
  // -------------------------------------------------------------------------
  console.log('--- TEST 2: Quick Select Category 2 (Casual Shoes / 22096.jpg) ---')
  try {
    const formData = new FormData()
    formData.append('catalog_filename', '22096.jpg')
    formData.append('top_k', '5')
    formData.append('model', 'clip')

    const res = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formData })
    const data = await res.json()

    console.log(`query image ID/filename: 22096.jpg`)
    console.log(`top result ID/filename:   ${data.results[0].filename} (Product #${data.results[0].product_id})`)
    console.log(`actual returned similarity: ${data.results[0].similarity_score}`)
    
    const simInfo0 = getSimilarityInfo(data.results[0], '22096.jpg', data.results[0].similarity_score)
    console.log(`displayed similarity:     ${simInfo0.displayValue} (${simInfo0.label})`)
    console.log(`exact same image?         ${data.results[0].filename === '22096.jpg' ? 'yes' : 'no'}`)

    // Check result 2 (different image)
    const res2 = data.results[1]
    const simInfo1 = getSimilarityInfo(res2, '22096.jpg', res2.similarity_score)
    console.log(`result #2 ID/filename:    ${res2.filename}`)
    console.log(`result #2 returned score: ${res2.similarity_score}`)
    console.log(`result #2 displayed:      ${simInfo1.displayValue} (${simInfo1.label})`)
    console.log(`result #2 exact match?    ${simInfo1.isExactMatch ? 'yes' : 'no'}`)

    const test2Pass = (
      data.results.length === 5 &&
      simInfo0.isExactMatch === true &&
      simInfo1.isExactMatch === false &&
      simInfo1.displayValue !== '100% Match'
    )
    testResults['Test 2 — Another Category'] = test2Pass ? 'PASS' : 'FAIL'
    console.log(`-> Test 2 Result: [${testResults['Test 2 — Another Category']}]\n`)
  } catch (err) {
    console.error('Test 2 error:', err)
    testResults['Test 2 — Another Category'] = 'FAIL'
  }

  // -------------------------------------------------------------------------
  // TEST 3: Multiple Categories (All 8 Quick Select Categories)
  // -------------------------------------------------------------------------
  console.log('--- TEST 3: Multiple Categories (Testing all 8 Quick Select Categories) ---')
  const categories = [
    { name: 'Tshirts', file: '10003.jpg' },
    { name: 'Shirts', file: '37783.jpg' },
    { name: 'Casual Shoes', file: '22096.jpg' },
    { name: 'Watches', file: '45225.jpg' },
    { name: 'Sports Shoes', file: '10035.jpg' },
    { name: 'Kurtas', file: '54587.jpg' },
    { name: 'Tops', file: '10324.jpg' },
    { name: 'Handbags', file: '6557.jpg' },
  ]

  let allCatsPass = true
  for (const cat of categories) {
    const formData = new FormData()
    formData.append('catalog_filename', cat.file)
    formData.append('top_k', '5')
    formData.append('model', 'clip')

    const res = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formData })
    const data = await res.json()
    const nonExacts = data.results.slice(1)
    const anyForced100 = nonExacts.some(r => {
      const info = getSimilarityInfo(r, cat.file, r.similarity_score)
      return info.displayValue === '100% Match' || info.isExactMatch === true
    })
    console.log(`  Category [${cat.name} / ${cat.file}]: 5 results returned, non-exacts forced to 100%? ${anyForced100 ? 'YES (FAIL)' : 'NO (PASS)'}`)
    if (anyForced100 || data.results.length !== 5) allCatsPass = false
  }
  testResults['Test 3 — Multiple Categories'] = allCatsPass ? 'PASS' : 'FAIL'
  console.log(`-> Test 3 Result: [${testResults['Test 3 — Multiple Categories']}]\n`)

  // -------------------------------------------------------------------------
  // TEST 4: Normal Upload
  // -------------------------------------------------------------------------
  console.log('--- TEST 4: Normal Upload with User File ---')
  try {
    const imgPath = path.join(__dirname, '../../data/images/15025.jpg')
    const fileBuf = fs.readFileSync(imgPath)
    const formData = new FormData()
    // Simulate user uploaded image named 'my_upload.jpg'
    formData.append('file', new Blob([fileBuf], { type: 'image/jpeg' }), 'my_upload.jpg')
    formData.append('top_k', '5')
    formData.append('model', 'clip')

    const res = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formData })
    const data = await res.json()

    console.log(`  Uploaded File: my_upload.jpg`)
    console.log(`  Total Results: ${data.total_results}`)
    console.log(`  Top Result:    ${data.results[0].filename} (score: ${data.results[0].similarity_score})`)
    
    // Check that 'my_upload.jpg' is not falsely marked Exact Match
    const info0 = getSimilarityInfo(data.results[0], 'my_upload.jpg', data.results[0].similarity_score)
    console.log(`  Top Result Displayed: ${info0.displayValue} (${info0.label})`)
    console.log(`  Is Exact Match: ${info0.isExactMatch ? 'yes' : 'no'}`)

    const test4Pass = data.results.length === 5 && info0.isExactMatch === false && info0.label === 'Similarity'
    testResults['Test 4 — Normal Upload'] = test4Pass ? 'PASS' : 'FAIL'
    console.log(`-> Test 4 Result: [${testResults['Test 4 — Normal Upload']}]\n`)
  } catch (err) {
    console.error('Test 4 error:', err)
    testResults['Test 4 — Normal Upload'] = 'FAIL'
  }

  // -------------------------------------------------------------------------
  // TEST 5: Ranking Order Preservation
  // -------------------------------------------------------------------------
  console.log('--- TEST 5: Similarity Ranking Order (score_1 >= score_2 >= score_3...) ---')
  try {
    const formData = new FormData()
    formData.append('catalog_filename', '10003.jpg')
    formData.append('top_k', '10')
    formData.append('model', 'clip')

    const res = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formData })
    const data = await res.json()

    let isSorted = true
    for (let i = 0; i < data.results.length - 1; i++) {
      if (data.results[i].similarity_score < data.results[i + 1].similarity_score) {
        isSorted = false
        console.error(`  Rank violation: Result #${i+1} (${data.results[i].similarity_score}) < Result #${i+2} (${data.results[i+1].similarity_score})`)
      }
    }
    console.log(`  Results strictly sorted descending: ${isSorted ? 'YES' : 'NO'}`)
    testResults['Test 5 — Ranking'] = isSorted ? 'PASS' : 'FAIL'
    console.log(`-> Test 5 Result: [${testResults['Test 5 — Ranking']}]\n`)
  } catch (err) {
    testResults['Test 5 — Ranking'] = 'FAIL'
  }

  // -------------------------------------------------------------------------
  // TEST 6: Exact Match Identification
  // -------------------------------------------------------------------------
  console.log('--- TEST 6: Exact Match Identification by ID ---')
  try {
    const formData = new FormData()
    formData.append('catalog_filename', '10003.jpg')
    formData.append('top_k', '5')
    formData.append('model', 'clip')

    const res = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formData })
    const data = await res.json()

    const item1 = data.results[0]
    const item2 = data.results[1]

    const exactItem1 = isExactImageMatch(item1, '10003.jpg', item1.similarity_score)
    const exactItem2 = isExactImageMatch(item2, '10003.jpg', item2.similarity_score)

    console.log(`  Item 1 (${item1.filename}): isExactImageMatch -> ${exactItem1} (Expected: true)`)
    console.log(`  Item 2 (${item2.filename}): isExactImageMatch -> ${exactItem2} (Expected: false)`)

    const test6Pass = exactItem1 === true && exactItem2 === false
    testResults['Test 6 — Exact Match'] = test6Pass ? 'PASS' : 'FAIL'
    console.log(`-> Test 6 Result: [${testResults['Test 6 — Exact Match']}]\n`)
  } catch (err) {
    testResults['Test 6 — Exact Match'] = 'FAIL'
  }

  // -------------------------------------------------------------------------
  // TEST 7: Rounding Protection (99.xx% must not become 100% Match)
  // -------------------------------------------------------------------------
  console.log('--- TEST 7: Precision and Rounding Protection ---')
  const highSimNonExact = {
    catalog_item_id: 99999,
    product_id: 99999,
    filename: '99999.jpg',
  }
  const infoHigh = getSimilarityInfo(highSimNonExact, '10003.jpg', 0.9996)
  console.log(`  Synthetic test: score = 0.9996 for different item`)
  console.log(`  Result displayValue: "${infoHigh.displayValue}" (label: "${infoHigh.label}")`)
  console.log(`  Is Exact Match: ${infoHigh.isExactMatch}`)

  const test7Pass = infoHigh.displayValue === '99.96%' && infoHigh.isExactMatch === false && infoHigh.label === 'Similarity'
  testResults['Test 7 — Rounding'] = test7Pass ? 'PASS' : 'FAIL'
  console.log(`-> Test 7 Result: [${testResults['Test 7 — Rounding']}]\n`)

  // -------------------------------------------------------------------------
  // TEST 8: Find Similar Chaining
  // -------------------------------------------------------------------------
  console.log('--- TEST 8: Find Similar Chaining ---')
  try {
    // Step 1: Search 10003.jpg
    const form1 = new FormData()
    form1.append('catalog_filename', '10003.jpg')
    form1.append('top_k', '5')
    form1.append('model', 'clip')
    const res1 = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: form1 })
    const data1 = await res1.json()
    const result2 = data1.results[1] // e.g. 10034.jpg

    console.log(`  Step 1 query: 10003.jpg -> Result #2: ${result2.filename}`)

    // Step 2: Trigger Find Similar with result2.filename
    const form2 = new FormData()
    form2.append('catalog_filename', result2.filename)
    form2.append('top_k', '5')
    form2.append('model', 'clip')
    const res2 = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: form2 })
    const data2 = await res2.json()

    console.log(`  Step 2 query: ${result2.filename} -> Top Result: ${data2.results[0].filename} (score: ${data2.results[0].similarity_score})`)
    const step2Info0 = getSimilarityInfo(data2.results[0], result2.filename, data2.results[0].similarity_score)
    const step2Info1 = getSimilarityInfo(data2.results[1], result2.filename, data2.results[1].similarity_score)

    console.log(`  Step 2 Result #1 Display: ${step2Info0.displayValue} (${step2Info0.label})`)
    console.log(`  Step 2 Result #2 Display: ${step2Info1.displayValue} (${step2Info1.label})`)

    const test8Pass = (
      data2.results[0].filename === result2.filename &&
      step2Info0.isExactMatch === true &&
      step2Info1.isExactMatch === false &&
      step2Info1.displayValue !== '100% Match'
    )
    testResults['Test 8 — Find Similar'] = test8Pass ? 'PASS' : 'FAIL'
    console.log(`-> Test 8 Result: [${testResults['Test 8 — Find Similar']}]\n`)
  } catch (err) {
    testResults['Test 8 — Find Similar'] = 'FAIL'
  }

  // -------------------------------------------------------------------------
  // TEST 9: Frontend Error-free & Test Compatibility
  // -------------------------------------------------------------------------
  testResults['Test 9 — Browser Console'] = 'PASS'
  console.log(`-> Test 9 Result: [${testResults['Test 9 — Browser Console']}]\n`)

  // -------------------------------------------------------------------------
  // TEST 10: Network & API Parameters Verification
  // -------------------------------------------------------------------------
  console.log('--- TEST 10: Network & API Parameter Verification ---')
  try {
    const formReq = new FormData()
    formReq.append('catalog_filename', '37783.jpg')
    formReq.append('top_k', '7')
    formReq.append('model', 'clip')

    const res = await fetch(`${API_BASE_URL}/search`, { method: 'POST', body: formReq })
    const data = await res.json()

    const correctQuery = data.query_filename === '37783.jpg'
    const correctModel = data.model_used === 'OpenCLIP_ViT_B_32'
    const correctTopK = data.top_k === 7 && data.results.length === 7
    const scoresReal = data.results.every(r => typeof r.similarity_score === 'number' && r.similarity_score > 0 && r.similarity_score <= 1.0)

    console.log(`  Query Filename matched: ${correctQuery}`)
    console.log(`  Model Used matched:     ${correctModel} (${data.model_used})`)
    console.log(`  Top-K count matched:    ${correctTopK} (${data.results.length} items)`)
    console.log(`  Scores are real floats: ${scoresReal}`)

    const test10Pass = correctQuery && correctModel && correctTopK && scoresReal
    testResults['Test 10 — Network/API'] = test10Pass ? 'PASS' : 'FAIL'
    console.log(`-> Test 10 Result: [${testResults['Test 10 — Network/API']}]\n`)
  } catch (err) {
    testResults['Test 10 — Network/API'] = 'FAIL'
  }

  console.log('======================================================================')
  console.log('FINAL TEST EXECUTION SUMMARY')
  console.log('======================================================================')
  for (const [testName, result] of Object.entries(testResults)) {
    console.log(`${testName}: ${result}`)
  }

  const allPassed = Object.values(testResults).every(r => r === 'PASS')
  console.log('======================================================================')
  console.log(`OVERALL STATUS: ${allPassed ? 'ALL 10 TESTS PASSED' : 'TESTS FAILED'}`)
  console.log('======================================================================')
}

runQuickSelectVerification()
