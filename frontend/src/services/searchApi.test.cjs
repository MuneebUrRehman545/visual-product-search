// Unit tests for frontend searchApi service logic

const API_BASE_URL = process.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

function getCatalogImageUrl(imagePathOrUrl) {
  if (!imagePathOrUrl) return ''
  if (imagePathOrUrl.startsWith('http://') || imagePathOrUrl.startsWith('https://')) {
    return imagePathOrUrl
  }
  const cleanPath = imagePathOrUrl.startsWith('/') ? imagePathOrUrl : `/${imagePathOrUrl}`
  return `${API_BASE_URL}${cleanPath}`
}

function validateSearchInputs(imageFile, topK) {
  if (!imageFile) {
    throw new Error('An image file must be provided for visual search.')
  }
  const topKNum = Number(topK)
  if (!Number.isInteger(topKNum) || topKNum < 1 || topKNum > 50) {
    throw new Error('top_k must be an integer between 1 and 50.')
  }
  return {
    url: `${API_BASE_URL}/api/v1/search`,
    fields: {
      file: imageFile.name,
      top_k: topKNum.toString()
    }
  }
}

console.log('==================================================')
console.log('FRONTEND SEARCH API SERVICE VALIDATION TEST SUITE')
console.log('==================================================')

let allPassed = true

// Test 1: Image URL Helper
const sampleUrl = getCatalogImageUrl('/catalog-images/15025.jpg')
const expectedUrl = `${API_BASE_URL}/catalog-images/15025.jpg`
const urlPassed = sampleUrl === expectedUrl
console.log(`[TEST 1] Helper URL: ${sampleUrl} [${urlPassed ? 'PASS' : 'FAIL'}]`)
if (!urlPassed) allPassed = false

// Test 2: Missing File
try {
  validateSearchInputs(null, 5)
  console.log('[TEST 2] Missing File Validation: FAIL (Did not throw)')
  allPassed = false
} catch (e) {
  console.log(`[TEST 2] Missing File Validation: PASS (${e.message})`)
}

// Test 3: topK = 0
try {
  validateSearchInputs({ name: 'test.jpg' }, 0)
  console.log('[TEST 3] topK=0 Validation: FAIL (Did not throw)')
  allPassed = false
} catch (e) {
  console.log(`[TEST 3] topK=0 Validation: PASS (${e.message})`)
}

// Test 4: topK = 51
try {
  validateSearchInputs({ name: 'test.jpg' }, 51)
  console.log('[TEST 4] topK=51 Validation: FAIL (Did not throw)')
  allPassed = false
} catch (e) {
  console.log(`[TEST 4] topK=51 Validation: PASS (${e.message})`)
}

// Test 5: Valid Inputs
try {
  const result = validateSearchInputs({ name: 'test.jpg' }, 5)
  const ok = result.url === `${API_BASE_URL}/api/v1/search` && result.fields.file === 'test.jpg' && result.fields.top_k === '5'
  console.log(`[TEST 5] Valid Inputs (topK=5): ${ok ? 'PASS' : 'FAIL'} (URL: ${result.url}, fields: file, top_k)`)
  if (!ok) allPassed = false
} catch (e) {
  console.log(`[TEST 5] Valid Inputs: FAIL (${e.message})`)
  allPassed = false
}

console.log('==================================================')
if (allPassed) {
  console.log('RESULT: ALL SEARCH API SERVICE TESTS PASSED.')
  process.exit(0)
} else {
  console.error('RESULT: TESTS FAILED.')
  process.exit(1)
}
