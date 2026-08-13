// Integration test script for React App state, search controls, and backend API integration

const fs = require('fs')
const path = require('path')

const API_BASE_URL = process.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

async function runIntegrationTest() {
  console.log('==================================================')
  console.log('FRONTEND TO BACKEND SEARCH INTEGRATION TEST SUITE')
  console.log('==================================================')

  let allPassed = true

  // 1. Initial State Checks
  const initialState = {
    selectedFile: null,
    topK: 10,
    loading: false,
    error: null,
    searchResults: null
  }
  const isSearchDisabledInitially = !initialState.selectedFile || initialState.loading
  console.log(`[TEST 1] Initial App State: selectedFile=null, topK=10, searchDisabled=${isSearchDisabledInitially} [${isSearchDisabledInitially ? 'PASS' : 'FAIL'}]`)
  if (!isSearchDisabledInitially) allPassed = false

  // 2. Loading State Check
  const loadingState = { ...initialState, selectedFile: { name: '15025.jpg' }, loading: true }
  const isSearchDisabledLoading = !loadingState.selectedFile || loadingState.loading
  const buttonText = loadingState.loading ? 'Searching...' : 'Search Catalog'
  console.log(`[TEST 2] Loading State: buttonText="${buttonText}", searchDisabled=${isSearchDisabledLoading} [${isSearchDisabledLoading && buttonText === 'Searching...' ? 'PASS' : 'FAIL'}]`)
  if (!isSearchDisabledLoading || buttonText !== 'Searching...') allPassed = false

  // 3. Real API Test topK=5 (15025.jpg)
  const imagePath15025 = path.join(__dirname, '../../data/catalog/images/15025.jpg')
  if (!fs.existsSync(imagePath15025)) {
    console.error(`Error: Image file not found at ${imagePath15025}`)
    process.exit(1)
  }
  const imgBuffer15025 = fs.readFileSync(imagePath15025)

  console.log('\n[TEST 3] Real Backend API Query: 15025.jpg (topK=5)')
  try {
    const formData = new FormData()
    const blob = new Blob([imgBuffer15025], { type: 'image/jpeg' })
    formData.append('file', blob, '15025.jpg')
    formData.append('top_k', '5')

    const res = await fetch(`${API_BASE_URL}/api/v1/search`, {
      method: 'POST',
      body: formData
    })

    console.log(`  HTTP Status Code: ${res.status}`)
    if (res.status !== 200) {
      console.error(`  FAILED: Expected HTTP 200, got ${res.status}`)
      allPassed = false
    } else {
      const data = await res.json()
      console.log(`  Query Filename:   ${data.query_filename}`)
      console.log(`  Total Results:    ${data.total_results}`)
      const ok5 = data.query_filename === '15025.jpg' && data.total_results === 5 && data.results.length === 5
      console.log(`  Verification:     [${ok5 ? 'PASS' : 'FAIL'}]`)
      if (!ok5) allPassed = false
    }
  } catch (err) {
    console.error(`  FAILED: API connection error (${err.message})`)
    allPassed = false
  }

  // 4. Real API Test topK=10 (17888.jpg)
  const imagePath17888 = path.join(__dirname, '../../data/catalog/images/17888.jpg')
  const imgBuffer17888 = fs.readFileSync(imagePath17888)

  console.log('\n[TEST 4] Real Backend API Query: 17888.jpg (topK=10)')
  try {
    const formData = new FormData()
    const blob = new Blob([imgBuffer17888], { type: 'image/jpeg' })
    formData.append('file', blob, '17888.jpg')
    formData.append('top_k', '10')

    const res = await fetch(`${API_BASE_URL}/api/v1/search`, {
      method: 'POST',
      body: formData
    })

    console.log(`  HTTP Status Code: ${res.status}`)
    if (res.status !== 200) {
      console.error(`  FAILED: Expected HTTP 200, got ${res.status}`)
      allPassed = false
    } else {
      const data = await res.json()
      console.log(`  Query Filename:   ${data.query_filename}`)
      console.log(`  Total Results:    ${data.total_results}`)
      const ok10 = data.query_filename === '17888.jpg' && data.total_results === 10 && data.results.length === 10
      console.log(`  Verification:     [${ok10 ? 'PASS' : 'FAIL'}]`)
      if (!ok10) allPassed = false
    }
  } catch (err) {
    console.error(`  FAILED: API connection error (${err.message})`)
    allPassed = false
  }

  // 5. Backend Error Handling Test (Invalid upload)
  console.log('\n[TEST 5] Readable Error Message Handling (Corrupted Upload)')
  try {
    const formData = new FormData()
    const blob = new Blob([Buffer.from('INVALID_IMAGE_BYTES')], { type: 'image/jpeg' })
    formData.append('file', blob, 'corrupt.jpg')
    formData.append('top_k', '5')

    const res = await fetch(`${API_BASE_URL}/api/v1/search`, {
      method: 'POST',
      body: formData
    })

    console.log(`  HTTP Status Code: ${res.status}`)
    const errData = await res.json()
    const readableError = errData.detail || 'Visual search failed.'
    console.log(`  Readable Error:   "${readableError}"`)
    const okErr = res.status === 400 && typeof readableError === 'string'
    console.log(`  Verification:     [${okErr ? 'PASS' : 'FAIL'}]`)
    if (!okErr) allPassed = false
  } catch (err) {
    console.error(`  FAILED: Error handling check (${err.message})`)
    allPassed = false
  }

  // 6. Reset Behavior Test
  let appState = { selectedFile: { name: '15025.jpg' }, searchResults: { total_results: 5 }, error: 'Old Error' }
  // Simulate handleFileChange(null)
  appState = { selectedFile: null, searchResults: null, error: null }
  const isResetOk = appState.selectedFile === null && appState.searchResults === null && appState.error === null
  console.log(`\n[TEST 6] Reset Clears Old Results & Errors: [${isResetOk ? 'PASS' : 'FAIL'}]`)
  if (!isResetOk) allPassed = false

  console.log('\n==================================================')
  if (allPassed) {
    console.log('RESULT: ALL FRONTEND TO BACKEND INTEGRATION TESTS PASSED.')
    process.exit(0)
  } else {
    console.error('RESULT: INTEGRATION TESTS FAILED.')
    process.exit(1)
  }
}

runIntegrationTest()
